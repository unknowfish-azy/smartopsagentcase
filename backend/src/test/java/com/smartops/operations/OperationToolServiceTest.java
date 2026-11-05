package com.smartops.operations;

import com.smartops.exception.BusinessException;
import com.smartops.service.OperationRunRecorder;
import com.smartops.service.OperationToolService;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OperationToolServiceTest {
    @Test
    void harbor_and_containerd_diagnostics_are_read_only_and_validate_targets() {
        var service = new OperationToolService(new OperationRuntimeRegistry());
        assertThat(service.preview(1L, "harbor-endpoint-check", Map.of("host", "registry.example.com"))
                .commands()).containsExactly("curl --fail --silent --show-error --max-time 10 https://registry.example.com/api/v2.0/health");
        assertThat(service.preview(1L, "containerd-registry-inspect", Map.of("namespace", "k8s.io"))
                .commands()).contains("ctr namespaces list", "ctr -n k8s.io images list");
        assertThatThrownBy(() -> service.preview(1L, "harbor-endpoint-check", Map.of("host", "registry.example.com;id")))
                .isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.preview(1L, "containerd-registry-inspect", Map.of("namespace", "k8s.io;id")))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void observability_tool_uses_http_adapter_instead_of_shell() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String runtimeId = registry.register(runtime);
        var adapter = org.mockito.Mockito.mock(com.smartops.service.ObservabilityService.class);
        var now = java.time.Instant.now();
        org.mockito.Mockito.when(adapter.query(1L, "prometheus", "up", 15, 200)).thenReturn(
                new com.smartops.service.ObservabilityService.QueryResult("http-trace", "prometheus", now, now,
                        new com.fasterxml.jackson.databind.ObjectMapper().createObjectNode().put("status", "success")));
        var service = new OperationToolService(registry, new RecordingRunRecorder(), adapter);
        var result = service.execute(1L, runtimeId, "prometheus-query", Map.of("query", "up"));
        assertThat(result.traceId()).isEqualTo("http-trace");
        assertThat(runtime.commands).isEmpty();
        assertThat(result.commands().get(0).command()).startsWith("HTTP");
    }

    @Test
    void cloud_tools_run_through_owned_runtime_and_record_evidence() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String runtimeId = registry.register(runtime);
        RecordingRunRecorder recorder = new RecordingRunRecorder();
        OperationToolService service = new OperationToolService(registry, recorder);
        for (String id : List.of("docker-compose-status", "helm-releases", "k8s-storage",
                "k8s-rbac-check", "mesh-status", "terraform-environment")) {
            var result = service.execute(1L, runtimeId, id, Map.of());
            assertThat(result.status()).isEqualTo("SUCCEEDED");
            assertThat(result.traceId()).isNotBlank();
            assertThat(recorder.finishedStatus).isEqualTo("SUCCEEDED");
        }
        assertThat(runtime.commands).contains("helm list -n default --max 100 -o json",
                "docker compose ls --all --format json", "terraform version -json");
        assertThatThrownBy(() -> service.execute(2L, runtimeId, "helm-releases", Map.of()))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void cloud_tools_reject_namespace_injection() {
        OperationToolService service = new OperationToolService(new OperationRuntimeRegistry());
        for (String id : List.of("helm-releases", "k8s-storage", "k8s-rbac-check", "mesh-status")) {
            assertThatThrownBy(() -> service.preview(1L, id, Map.of("namespace", "default;id")))
                    .isInstanceOf(BusinessException.class).hasMessageContaining("INVALID_TOOL_PARAMETER");
        }
    }

    @Test
    void previews_a_server_defined_kubernetes_command() {
        OperationToolService service = new OperationToolService(new OperationRuntimeRegistry());

        OperationToolService.ToolPreview preview = service.preview(
                1L,
                "k8s-resources",
                Map.of("namespace", "production", "resource", "pod", "name", "api-0")
        );

        assertThat(preview.toolId()).isEqualTo("k8s-resources");
        assertThat(preview.readOnly()).isTrue();
        assertThat(preview.commands()).containsExactly(
                "kubectl get pod api-0 -n production -o wide",
                "kubectl describe pod api-0 -n production"
        );
    }

    @Test
    void rejects_shell_metacharacters_on_the_server() {
        OperationToolService service = new OperationToolService(new OperationRuntimeRegistry());

        assertThatThrownBy(() -> service.preview(
                1L,
                "docker-logs",
                Map.of("container", "api; rm -rf /", "tail", "200")
        )).isInstanceOf(BusinessException.class)
                .hasMessageContaining("INVALID_TOOL_PARAMETER");
    }

    @Test
    void executes_only_read_only_tools_and_returns_traceable_evidence() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        RecordingRuntime runtime = new RecordingRuntime(1L);
        String runtimeId = registry.register(runtime);
        RecordingRunRecorder recorder = new RecordingRunRecorder();
        OperationToolService service = new OperationToolService(registry, recorder);

        OperationToolService.ToolRunResult result = service.execute(
                1L,
                runtimeId,
                "host-health",
                Map.of()
        );

        assertThat(result.traceId()).isNotBlank();
        assertThat(result.status()).isEqualTo("SUCCEEDED");
        assertThat(result.runtimeId()).isEqualTo(runtimeId);
        assertThat(result.commands()).hasSize(4);
        assertThat(result.commands().get(0).stdout()).isEqualTo("ok: uptime");
        assertThat(runtime.commands).containsExactly("uptime", "free -h", "df -hT", "ss -lntup");
        assertThat(recorder.startedTraceId).isEqualTo(result.traceId());
        assertThat(recorder.outputs).hasSize(4);
        assertThat(recorder.outputs.get(0).stdout()).isEqualTo("ok: uptime");
        assertThat(recorder.finishedStatus).isEqualTo("SUCCEEDED");
    }

    @Test
    void blocks_mutating_tools_from_the_read_only_execution_endpoint() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        String runtimeId = registry.register(new RecordingRuntime(1L));
        OperationToolService service = new OperationToolService(registry);

        assertThatThrownBy(() -> service.execute(
                1L,
                runtimeId,
                "service-restart",
                Map.of("service", "nginx")
        )).isInstanceOf(BusinessException.class)
                .hasMessageContaining("TOOL_CONFIRMATION_REQUIRED");
    }

    @Test
    void previews_agent_read_only_tools_with_safe_search_arguments() {
        OperationToolService service = new OperationToolService(new OperationRuntimeRegistry());

        assertThat(service.preview(1L, "log-search", Map.of(
                "service", "api", "keyword", "connection refused", "lines", "50"
        )).commands()).containsExactly(
                "journalctl -u api -n 50 --no-pager | grep -i -- 'connection refused'"
        );
        assertThat(service.preview(1L, "network-diagnostics", Map.of(
                "host", "api.example.com", "port", "443"
        )).commands()).containsExactly(
                "ping -c 3 api.example.com",
                "nc -vz -w 5 api.example.com 443",
                "dig api.example.com"
        );
        assertThat(service.preview(1L, "database-readonly", Map.of("metric", "connections")).commands().get(0))
                .contains("/api/operations/database/diagnose");
    }

    @Test
    void rejects_search_quote_injection_and_keeps_alert_suppression_confirmed() {
        OperationToolService service = new OperationToolService(new OperationRuntimeRegistry());
        assertThatThrownBy(() -> service.preview(1L, "log-search", Map.of(
                "service", "api", "keyword", "x' ; rm -rf /"
        ))).isInstanceOf(BusinessException.class).hasMessageContaining("INVALID_TOOL_PARAMETER");

        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        String runtimeId = registry.register(new RecordingRuntime(1L));
        assertThatThrownBy(() -> service.execute(1L, runtimeId, "alerts-suppress", Map.of("alert", "HighCPU")))
                .isInstanceOf(BusinessException.class).hasMessageContaining("TOOL_CONFIRMATION_REQUIRED");
    }

    @Test
    void previews_observability_and_kubernetes_diagnostic_tools_as_read_only() {
        OperationToolService service = new OperationToolService(new OperationRuntimeRegistry());
        assertThat(service.preview(1L, "prometheus-query", Map.of("query", "up", "range", "15")).readOnly()).isTrue();
        assertThat(service.preview(1L, "mysql-slow-query", Map.of("database", "orders", "limit", "20")).commands())
                .singleElement().satisfies(command -> assertThat(command)
                        .contains("metric=SLOW_SQL")
                        .contains("/api/operations/database/diagnose"));
        assertThat(service.preview(1L, "k8s-diagnose", Map.of("namespace", "demo", "name", "api")).commands())
                .containsExactly(
                        "kubectl get pod,deploy,svc,endpoints -n demo -l app=api -o wide",
                        "kubectl get events -n demo --sort-by=.lastTimestamp");
    }

    private static final class RecordingRuntime implements OperationRuntime {
        private final Long userId;
        private final List<String> commands = new ArrayList<>();

        private RecordingRuntime(Long userId) { this.userId = userId; }
        public String id() { return "runtime"; }
        public Long userId() { return userId; }
        public Long sessionId() { return 1L; }
        public void write(String input) { }
        public void resize(int columns, int rows) { }
        public void onOutput(OutputListener listener) { }
        public boolean isOpen() { return true; }
        public void close() { }

        @Override
        public CommandResult execute(String command, long timeoutMillis) throws IOException {
            commands.add(command);
            return new CommandResult(0, "ok: " + command, "");
        }
    }

    private static final class RecordingRunRecorder implements OperationRunRecorder {
        private String startedTraceId;
        private final List<CommandOutput> outputs = new ArrayList<>();
        private String finishedStatus;

        @Override
        public RunHandle start(String traceId, Long userId, OperationRuntime runtime, String toolId,
                               java.time.Instant startedAt) {
            startedTraceId = traceId;
            return new RunHandle(91L, traceId);
        }

        @Override
        public void recordCommand(RunHandle run, int sequence, String command, int exitCode,
                                  String stdout, String stderr, java.time.Instant startedAt,
                                  java.time.Instant endedAt) {
            outputs.add(new CommandOutput(command, exitCode, stdout, stderr));
        }

        @Override
        public void finish(RunHandle run, String status, java.time.Instant endedAt) {
            finishedStatus = status;
        }

        private record CommandOutput(String command, int exitCode, String stdout, String stderr) {}
    }
}
