package com.smartops.diagnostics.kubernetes;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.diagnostics.kubernetes.KubernetesDiagnosisService.KubernetesCheck;
import com.smartops.diagnostics.kubernetes.KubernetesDiagnosisService.KubernetesDiagnosisResult;
import com.smartops.diagnostics.kubernetes.KubernetesDiagnosisService.KubernetesFinding;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class KubernetesDiagnosisServiceTest {

    private static final String CONTEXT = "kind-prod";
    private static final String NAMESPACE = "demo";

    @Test
    void crash_loop_and_oom_are_both_reported_with_evidence() {
        StubRuntime runtime = new StubRuntime(1L)
                .reply("get pods", 0, crashLoopPodsJson(), "")
                .reply("--previous", 0, "panic: out of memory\n", "");

        KubernetesDiagnosisResult result = diagnose(runtime, request(null, "api-0"));

        assertThat(result.findings()).extracting(KubernetesFinding::type)
                .contains("CRASH_LOOP", "OOM");
        KubernetesFinding crash = result.findings().stream()
                .filter(finding -> "CRASH_LOOP".equals(finding.type()))
                .findFirst().orElseThrow();
        assertThat(crash.resourceKind()).isEqualTo("Pod");
        assertThat(crash.resourceName()).isEqualTo("api-0");
        assertThat(crash.evidenceCommand()).contains("kubectl get pods");
        assertThat(Instant.parse(crash.evidenceAt())).isNotNull();

        assertThat(result.checks()).filteredOn(check -> "POD_STATUS".equals(check.name()))
                .singleElement()
                .extracting(KubernetesCheck::status)
                .isEqualTo("FAULT");
        assertThat(result.checks()).filteredOn(check -> "PREVIOUS_LOGS".equals(check.name()))
                .singleElement()
                .satisfies(check -> {
                    assertThat(check.status()).isEqualTo("OK");
                    assertThat(check.command()).contains("--previous");
                });
        assertThat(result.permissionDenied()).isFalse();
        assertThat(result.dataMissing()).isFalse();
    }

    @Test
    void pending_pod_with_insufficient_nodes_reports_pending_and_node_pressure() {
        StubRuntime runtime = new StubRuntime(1L)
                .reply("get pods", 0, pendingPodsJson(), "")
                .reply("get events", 0, failedSchedulingEvents(Instant.now()), "");

        KubernetesDiagnosisResult result = diagnose(runtime, request(null, null));

        assertThat(result.findings()).extracting(KubernetesFinding::type)
                .contains("PENDING", "NODE_PRESSURE");
        assertThat(result.findings()).extracting(KubernetesFinding::type)
                .doesNotContain("CRASH_LOOP", "IMAGE_PULL", "PVC_MOUNT");
    }

    @Test
    void image_pull_backoff_is_reported_as_image_pull() {
        StubRuntime runtime = new StubRuntime(1L)
                .reply("get pods", 0, imagePullPodsJson(), "");

        KubernetesDiagnosisResult result = diagnose(runtime, request(null, null));

        assertThat(result.findings()).extracting(KubernetesFinding::type)
                .contains("IMAGE_PULL");
        assertThat(result.findings()).extracting(KubernetesFinding::severity)
                .contains("CRITICAL");
    }

    @Test
    void unhealthy_probe_event_is_reported_as_probe_failure() {
        StubRuntime runtime = new StubRuntime(1L)
                .reply("get pods", 0, runningPodsJson(), "")
                .reply("get events", 0, unhealthyEvents(Instant.now()), "");

        KubernetesDiagnosisResult result = diagnose(runtime, request(null, null));

        assertThat(result.findings()).extracting(KubernetesFinding::type)
                .contains("PROBE_FAILURE");
        KubernetesFinding finding = result.findings().stream()
                .filter(item -> "PROBE_FAILURE".equals(item.type()))
                .findFirst().orElseThrow();
        assertThat(finding.detail()).contains("Readiness probe failed");
        assertThat(finding.evidenceAt()).isNotBlank();
    }

    @Test
    void pending_pvc_and_failed_mount_event_both_report_pvc_mount() {
        StubRuntime runtime = new StubRuntime(1L)
                .reply("get pvc", 0, pendingPvcJson(), "")
                .reply("get events", 0, failedMountEvents(Instant.now()), "");

        KubernetesDiagnosisResult result = diagnose(runtime, request(null, null));

        assertThat(result.findings()).filteredOn(finding -> "PVC_MOUNT".equals(finding.type()))
                .hasSize(2);
        assertThat(result.findings()).filteredOn(finding -> "PVC_MOUNT".equals(finding.type()))
                .extracting(KubernetesFinding::evidenceCommand)
                .anyMatch(command -> command.startsWith("kubectl get pvc"));
        assertThat(result.findings()).filteredOn(finding -> "PVC_MOUNT".equals(finding.type()))
                .extracting(KubernetesFinding::evidenceCommand)
                .anyMatch(command -> command.startsWith("kubectl get events"));
    }

    @Test
    void forbidden_access_is_no_permission_not_a_fault() {
        StubRuntime runtime = new StubRuntime(1L)
                .fallback(1, "", "Error from server (Forbidden): pods is forbidden: cannot list resource pods");

        KubernetesDiagnosisResult result = diagnose(runtime, request(null, null));

        assertThat(result.permissionDenied()).isTrue();
        assertThat(result.findings()).isEmpty();
        assertThat(result.dataMissing()).isFalse();
        assertThat(result.checks()).allMatch(check ->
                "NO_PERMISSION".equals(check.status()) || "OK".equals(check.status()));
        assertThat(result.checks()).noneMatch(check ->
                "FAULT".equals(check.status()) || "DATA_MISSING".equals(check.status()));
        assertThat(result.checks()).filteredOn(check -> "POD_STATUS".equals(check.name()))
                .singleElement()
                .extracting(KubernetesCheck::status)
                .isEqualTo("NO_PERMISSION");
    }

    @Test
    void missing_pod_is_data_missing_and_not_a_crash_loop() {
        StubRuntime runtime = new StubRuntime(1L)
                .reply("get pods", 1, "", "Error from server (NotFound): pods api-0 not found");

        KubernetesDiagnosisResult result = diagnose(runtime, request(null, "api-0"));

        assertThat(result.dataMissing()).isTrue();
        assertThat(result.permissionDenied()).isFalse();
        assertThat(result.findings()).isEmpty();
        assertThat(result.findings()).extracting(KubernetesFinding::type)
                .doesNotContain("CRASH_LOOP", "OOM", "PENDING");
        assertThat(result.checks()).filteredOn(check -> "POD_STATUS".equals(check.name()))
                .singleElement()
                .extracting(KubernetesCheck::status)
                .isEqualTo("DATA_MISSING");
    }

    @Test
    void closed_runtime_is_rejected_with_conflict() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        StubRuntime runtime = new StubRuntime(1L, false);
        String runtimeId = registry.register(runtime);
        KubernetesDiagnosisService service = new KubernetesDiagnosisService(registry, new ObjectMapper());

        assertThatThrownBy(() -> service.diagnose(1L, runtimeId, request(null, null)))
                .isInstanceOf(BusinessException.class)
                .hasMessage("RUNTIME_CLOSED");
    }

    /* ── 测试替身与夹具 ─────────────────────────────────────────────────── */

    private static KubernetesDiagnosisResult diagnose(StubRuntime runtime, KubernetesDiagnosisRequest request) {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        String runtimeId = registry.register(runtime);
        return new KubernetesDiagnosisService(registry, new ObjectMapper())
                .diagnose(runtime.userId(), runtimeId, request);
    }

    private static KubernetesDiagnosisRequest request(String workload, String pod) {
        return new KubernetesDiagnosisRequest(CONTEXT, NAMESPACE, workload, pod, null, 60);
    }

    private static String crashLoopPodsJson() {
        return """
                {"items":[{
                  "metadata":{"name":"api-0","namespace":"demo"},
                  "status":{"phase":"Running","containerStatuses":[
                    {"name":"api","restartCount":7,
                     "state":{"waiting":{"reason":"CrashLoopBackOff","message":"back-off 5m0s restarting failed container"}},
                     "lastState":{"terminated":{"reason":"OOMKilled","exitCode":137}}}
                  ]}
                }]}
                """;
    }

    private static String pendingPodsJson() {
        return """
                {"items":[{"metadata":{"name":"web-0","namespace":"demo"},
                  "status":{"phase":"Pending","containerStatuses":[]}}]}
                """;
    }

    private static String imagePullPodsJson() {
        return """
                {"items":[{"metadata":{"name":"api-0","namespace":"demo"},
                  "status":{"phase":"Running","containerStatuses":[
                    {"name":"api","restartCount":0,
                     "state":{"waiting":{"reason":"ImagePullBackOff","message":"Back-off pulling image registry/api:1"}}}
                  ]}}]}
                """;
    }

    private static String runningPodsJson() {
        return """
                {"items":[{"metadata":{"name":"api-0","namespace":"demo"},
                  "status":{"phase":"Running","containerStatuses":[
                    {"name":"api","restartCount":0,"state":{"running":{"startedAt":"2026-11-05T00:00:00Z"}}}
                  ]}}]}
                """;
    }

    private static String pendingPvcJson() {
        return """
                {"items":[{"metadata":{"name":"data-0","namespace":"demo"},"status":{"phase":"Pending"}}]}
                """;
    }

    private static String failedSchedulingEvents(Instant at) {
        return """
                {"items":[{"reason":"FailedScheduling",
                  "message":"0/3 nodes are available: 3 Insufficient memory.",
                  "involvedObject":{"kind":"Pod","name":"web-0"},"lastTimestamp":"%s"}]}
                """.formatted(at);
    }

    private static String unhealthyEvents(Instant at) {
        return """
                {"items":[{"reason":"Unhealthy",
                  "message":"Readiness probe failed: Get http://10.0.0.1:8080/ready: connection refused",
                  "involvedObject":{"kind":"Pod","name":"api-0"},"lastTimestamp":"%s"}]}
                """.formatted(at);
    }

    private static String failedMountEvents(Instant at) {
        return """
                {"items":[{"reason":"FailedMount",
                  "message":"MountVolume.SetUp failed for volume data",
                  "involvedObject":{"kind":"Pod","name":"data-0"},"lastTimestamp":"%s"}]}
                """.formatted(at);
    }

    private static final class StubRuntime implements OperationRuntime {
        private final Long userId;
        private final boolean open;
        private final Map<String, CommandResult> replies = new LinkedHashMap<>();
        private final List<String> commands = new ArrayList<>();
        private CommandResult fallback = new CommandResult(0, "{\"items\":[]}", "");

        private StubRuntime(Long userId) {
            this(userId, true);
        }

        private StubRuntime(Long userId, boolean open) {
            this.userId = userId;
            this.open = open;
        }

        private StubRuntime reply(String commandFragment, int exitCode, String stdout, String stderr) {
            replies.put(commandFragment, new CommandResult(exitCode, stdout, stderr));
            return this;
        }

        private StubRuntime fallback(int exitCode, String stdout, String stderr) {
            this.fallback = new CommandResult(exitCode, stdout, stderr);
            return this;
        }

        @Override
        public CommandResult execute(String command, long timeoutMillis) {
            commands.add(command);
            for (Map.Entry<String, CommandResult> reply : replies.entrySet()) {
                if (command.contains(reply.getKey())) return reply.getValue();
            }
            return fallback;
        }

        public String id() { return "stub-runtime"; }
        public Long userId() { return userId; }
        public Long sessionId() { return 1L; }
        public void write(String input) { }
        public void resize(int columns, int rows) { }
        public void onOutput(OutputListener listener) { }
        public boolean isOpen() { return open; }
        public void close() { }
    }
}
