package com.smartops.service;

import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import com.smartops.runbook.RunbookExecutionService;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class MultiExecServiceTest {
    private final RunbookExecutionService runbook = mock(RunbookExecutionService.class);

    @Test
    void critical_preview_does_not_write_before_second_confirmation() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String id = registry.register(runtime);
        MultiExecService service = new MultiExecService(registry, runbook, 10, 120_000, 900_000, 200);
        MultiExecService.Preview preview = service.preview(1L, "kubectl delete pod api", List.of(id), true);

        assertThatThrownBy(() -> service.execute(1L, preview.id(), preview.confirmationNonce(), "wrong"))
                .hasMessageContaining("SECOND_CONFIRMATION_REQUIRED");
        assertThat(runtime.writes).isEmpty();
    }

    @Test
    void second_confirmation_by_the_previewer_itself_is_rejected_as_self_approval() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String id = registry.register(runtime);
        MultiExecService service = new MultiExecService(registry, runbook, 10, 120_000, 900_000, 200);
        MultiExecService.Preview preview = service.preview(1L, "rm -rf /tmp/data", List.of(id), false);

        // 回显同一个 nonce 不构成第二人复核：执行者=预览者即自批（SEC-03）。
        assertThatThrownBy(() -> service.execute(1L, preview.id(), preview.confirmationNonce(), preview.confirmationNonce()))
                .hasMessageContaining("SECOND_APPROVER_REQUIRED");
        assertThat(runtime.writes).isEmpty();
    }

    @Test
    void different_subject_with_the_nonce_can_execute_critical_preview() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String id = registry.register(runtime);
        MultiExecService service = new MultiExecService(registry, runbook, 10, 120_000, 900_000, 200);
        MultiExecService.Preview preview = service.preview(1L, "rm -rf /tmp/data", List.of(id), false);
        // SEC-03 修复：执行以预览创建者（通道归属）身份进行，第二审批人作为触发者
        // 传入 secondApproverId——否则第二审批人永远过不了 requireOwned。
        when(runbook.prepareAdHocBatch(eq(1L), anyString(), anyString(), anyList(), anyInt(), anyBoolean(),
                anyString(), anyInt(), anyInt(), eq(2L)))
                .thenReturn(7L);
        when(runbook.execute(eq(1L), anyLong(), anyString())).thenReturn(runView());

        MultiExecService.ExecutionResult result = service.execute(2L, preview.id(), preview.confirmationNonce(), preview.confirmationNonce());

        assertThat(result.runId()).isEqualTo(7L);
        assertThat(result.status()).isEqualTo("SUCCEEDED");
        org.mockito.Mockito.verify(runbook).prepareAdHocBatch(eq(1L), anyString(), anyString(), anyList(),
                anyInt(), anyBoolean(), anyString(), anyInt(), anyInt(), eq(2L));
    }

    @Test
    void low_risk_preview_rejects_non_owner_executor() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String id = registry.register(runtime);
        MultiExecService service = new MultiExecService(registry, runbook, 10, 120_000, 900_000, 200);
        MultiExecService.Preview preview = service.preview(1L, "uptime", List.of(id), false);

        // 低风险预览没有第二人确认环节：他人拿到 previewId+nonce 也不能执行。
        assertThatThrownBy(() -> service.execute(2L, preview.id(), preview.confirmationNonce(), null))
                .hasMessageContaining("PREVIEW_OWNER_REQUIRED");
        assertThat(runtime.writes).isEmpty();
    }

    @Test
    void replayed_preview_id_executes_only_once() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String id = registry.register(runtime);
        MultiExecService service = new MultiExecService(registry, runbook, 10, 120_000, 900_000, 200);
        MultiExecService.Preview preview = service.preview(1L, "uptime", List.of(id), false);
        when(runbook.prepareAdHocBatch(eq(1L), anyString(), anyString(), anyList(), anyInt(), anyBoolean(),
                anyString(), anyInt(), anyInt(), org.mockito.ArgumentMatchers.isNull()))
                .thenReturn(7L);
        when(runbook.execute(eq(1L), anyLong(), anyString())).thenReturn(runView());

        service.execute(1L, preview.id(), preview.confirmationNonce(), null);

        // 预览被成功执行后即从预览表消费掉：重放得到 404，且底层执行只发生一次。
        assertThatThrownBy(() -> service.execute(1L, preview.id(), preview.confirmationNonce(), null))
                .hasMessageContaining("PREVIEW_NOT_FOUND");
        org.mockito.Mockito.verify(runbook, org.mockito.Mockito.times(1)).execute(eq(1L), anyLong(), anyString());
    }

    @Test
    void expired_preview_is_rejected_even_with_valid_nonce() throws InterruptedException {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String id = registry.register(runtime);
        MultiExecService service = new MultiExecService(registry, runbook, 10, 120_000, 1, 200);
        MultiExecService.Preview preview = service.preview(1L, "uptime", List.of(id), false);

        Thread.sleep(20);

        assertThatThrownBy(() -> service.execute(1L, preview.id(), preview.confirmationNonce(), null))
                .hasMessageContaining("PREVIEW_EXPIRED");
    }

    @Test
    void preview_store_is_bounded() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String id = registry.register(runtime);
        MultiExecService service = new MultiExecService(registry, runbook, 10, 120_000, 900_000, 2);

        service.preview(1L, "uptime", List.of(id), false);
        service.preview(1L, "whoami", List.of(id), false);

        assertThatThrownBy(() -> service.preview(1L, "date", List.of(id), false))
                .hasMessageContaining("PREVIEW_LIMIT_EXCEEDED");
    }

    private RunbookExecutionService.RunView runView() {
        return new RunbookExecutionService.RunView(7L, 0L, "adhoc", 1, 2L, "prod",
                "MANUAL", null, "SUCCEEDED", "CRITICAL", 2, 2, false, "hash",
                Instant.now(), Instant.now(), Instant.now(), null, 1, 1,
                0, 0, 0, 0, List.of());
    }

    private static final class RecordingRuntime implements OperationRuntime {
        private final Long userId;
        private final List<String> writes = new ArrayList<>();
        private RecordingRuntime(Long userId) { this.userId = userId; }
        public String id() { return "runtime"; }
        public Long userId() { return userId; }
        public Long sessionId() { return 1L; }
        public void write(String input) { writes.add(input); }
        public void resize(int columns, int rows) {}
        public void onOutput(OutputListener listener) {}
        public boolean isOpen() { return true; }
        public void close() {}
    }
}
