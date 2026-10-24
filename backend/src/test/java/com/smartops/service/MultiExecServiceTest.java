package com.smartops.service;

import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MultiExecServiceTest {
    @Test
    void critical_preview_does_not_write_before_second_confirmation() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String id = registry.register(runtime);
        MultiExecService service = new MultiExecService(registry);
        MultiExecService.Preview preview = service.preview(1L, "kubectl delete pod api", List.of(id), true);

        assertThatThrownBy(() -> service.execute(1L, preview.id(), preview.confirmationNonce(), "wrong"))
                .hasMessageContaining("SECOND_CONFIRMATION_REQUIRED");
        org.assertj.core.api.Assertions.assertThat(runtime.writes).isEmpty();
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
