package com.smartops.diagnostics.network;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.diagnostics.network.NetworkPathService.NetworkCheck;
import com.smartops.diagnostics.network.NetworkPathService.NetworkLayer;
import com.smartops.diagnostics.network.NetworkPathService.NetworkPathResult;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class NetworkPathServiceTest {

    private static final String CONTEXT = "kind-prod";
    private static final String NAMESPACE = "demo";
    private static final String HOST = "api.example.com";
    private static final String SERVICE = "api-svc";
    private static final String INGRESS = "api-ing";

    @Test
    void healthy_path_has_no_failed_layer_and_cloud_layers_stay_unverified() {
        StubRuntime runtime = fullPathRuntime();

        NetworkPathResult result = diagnose(runtime, fullRequest());

        assertThat(result.layers()).hasSize(9);
        assertThat(result.layers()).extracting(NetworkLayer::name).containsExactly(
                "DNS", "INGRESS", "SERVICE", "ENDPOINT_SLICE", "POD", "NETWORK_POLICY", "TLS",
                "SECURITY_GROUP", "ROUTE");
        assertThat(result.layers()).extracting(NetworkLayer::status).doesNotContain("FAILED");
        assertThat(layer(result, "DNS").status()).isEqualTo("OK");
        assertThat(layer(result, "SECURITY_GROUP").status()).isEqualTo("UNVERIFIED");
        assertThat(layer(result, "ROUTE").status()).isEqualTo("UNVERIFIED");
        assertThat(result.permissionDenied()).isFalse();
        assertThat(result.dataMissing()).isFalse();
    }

    @Test
    void nxdomain_fails_dns_and_blocks_tls_only() {
        StubRuntime runtime = fullPathRuntime()
                .reply("getent hosts", 2, "", "Host " + HOST + " not found: 3(NXDOMAIN)");

        NetworkPathResult result = diagnose(runtime, fullRequest());

        assertThat(layer(result, "DNS").status()).isEqualTo("FAILED");
        assertThat(layer(result, "TLS").blockedBy()).isEqualTo("DNS");
        assertThat(layer(result, "INGRESS").status()).isEqualTo("OK");
        assertThat(layer(result, "SERVICE").status()).isEqualTo("OK");
        assertThat(layer(result, "ENDPOINT_SLICE").status()).isEqualTo("OK");
        assertThat(layer(result, "POD").status()).isEqualTo("OK");
    }

    @Test
    void ingress_without_load_balancer_address_fails_but_service_is_still_collected() {
        StubRuntime runtime = fullPathRuntime()
                .reply("get ingress", 0, """
                        {"metadata":{"name":"api-ing","namespace":"demo"},
                         "status":{"loadBalancer":{}}}
                        """, "");

        NetworkPathResult result = diagnose(runtime, fullRequest());

        assertThat(layer(result, "INGRESS").status()).isEqualTo("FAILED");
        assertThat(layer(result, "INGRESS").summary()).contains("负载均衡");
        assertThat(layer(result, "SERVICE").status()).isEqualTo("OK");
        assertThat(layer(result, "ENDPOINT_SLICE").status()).isEqualTo("OK");
    }

    @Test
    void service_without_selector_blocks_endpoint_slice_and_pods() {
        StubRuntime runtime = fullPathRuntime()
                .reply("get svc", 0, """
                        {"metadata":{"name":"api-svc","namespace":"demo"},
                         "spec":{"type":"ClusterIP","clusterIP":"10.0.0.20",
                                 "ports":[{"name":"http","port":80,"targetPort":8080,"protocol":"TCP"}]}}
                        """, "");

        NetworkPathResult result = diagnose(runtime, fullRequest());

        assertThat(layer(result, "SERVICE").status()).isEqualTo("FAILED");
        assertThat(layer(result, "ENDPOINT_SLICE").blockedBy()).isEqualTo("SERVICE");
        assertThat(layer(result, "POD").blockedBy()).isEqualTo("SERVICE");
        assertThat(layer(result, "ENDPOINT_SLICE").summary()).contains("上游 SERVICE");
    }

    @Test
    void endpoint_slice_with_only_not_ready_endpoints_fails_with_pod_evidence() {
        StubRuntime runtime = fullPathRuntime()
                .reply("get endpointslices", 0, """
                        {"items":[{"metadata":{"name":"api-svc-abc","namespace":"demo"},
                          "endpoints":[{"conditions":{"ready":false},
                                        "targetRef":{"kind":"Pod","name":"api-7d9f5-x2k"}}]}]}
                        """, "");

        NetworkPathResult result = diagnose(runtime, fullRequest());

        assertThat(layer(result, "ENDPOINT_SLICE").status()).isEqualTo("FAILED");
        assertThat(layer(result, "ENDPOINT_SLICE").checks())
                .extracting(NetworkCheck::evidence)
                .anyMatch(evidence -> evidence.contains("api-7d9f5-x2k"));
        assertThat(layer(result, "POD").blockedBy()).isEqualTo("ENDPOINT_SLICE");
    }

    @Test
    void network_policy_matching_pods_is_ok_but_requires_manual_confirmation() {
        StubRuntime runtime = fullPathRuntime()
                .reply("get networkpolicy", 0, """
                        {"items":[{"metadata":{"name":"deny-all","namespace":"demo"},
                          "spec":{"podSelector":{"matchLabels":{}},
                                  "policyTypes":["Ingress"]}}]}
                        """, "");

        NetworkPathResult result = diagnose(runtime, fullRequest());

        assertThat(layer(result, "NETWORK_POLICY").status()).isEqualTo("OK");
        assertThat(layer(result, "NETWORK_POLICY").summary()).contains("需人工确认");
        assertThat(layer(result, "NETWORK_POLICY").summary()).contains("deny-all");
    }

    @Test
    void tls_verify_code_20_fails_with_code_in_evidence() {
        StubRuntime runtime = fullPathRuntime()
                .reply("openssl s_client", 1, "",
                        "Verify return code: 20 (unable to get local issuer certificate)");

        NetworkPathResult result = diagnose(runtime, fullRequest());

        assertThat(layer(result, "TLS").status()).isEqualTo("FAILED");
        assertThat(layer(result, "TLS").checks())
                .extracting(NetworkCheck::evidence)
                .anyMatch(evidence -> evidence.contains("20"));
        assertThat(layer(result, "TLS").blockedBy()).isNull();
    }

    @Test
    void forbidden_is_no_permission_and_never_a_failure() {
        StubRuntime runtime = new StubRuntime(1L)
                .reply("getent hosts", 0, "10.0.0.10 " + HOST, "")
                .reply("openssl s_client", 0, "Verify return code: 0 (ok)", "")
                .fallback(1, "", "Error from server (Forbidden): pods is forbidden: "
                        + "User \"ops\" cannot list resource \"pods\"");

        NetworkPathResult result = diagnose(runtime, fullRequest());

        assertThat(result.permissionDenied()).isTrue();
        assertThat(result.layers()).extracting(NetworkLayer::status).doesNotContain("FAILED");
        assertThat(layer(result, "POD").status()).isEqualTo("NO_PERMISSION");
        assertThat(layer(result, "SERVICE").status()).isEqualTo("NO_PERMISSION");
        assertThat(layer(result, "ENDPOINT_SLICE").status()).isEqualTo("NO_PERMISSION");
    }

    @Test
    void missing_inputs_are_not_applicable_never_ok() {
        StubRuntime runtime = new StubRuntime(1L);

        NetworkPathResult result = diagnose(runtime,
                new NetworkPathRequest(CONTEXT, NAMESPACE, null, 0, null, null, null, false, 0));

        assertThat(layer(result, "DNS").status()).isEqualTo("NOT_APPLICABLE");
        assertThat(layer(result, "INGRESS").status()).isEqualTo("NOT_APPLICABLE");
        assertThat(layer(result, "SERVICE").status()).isEqualTo("NOT_APPLICABLE");
        assertThat(layer(result, "ENDPOINT_SLICE").status()).isEqualTo("NOT_APPLICABLE");
        assertThat(layer(result, "TLS").status()).isEqualTo("NOT_APPLICABLE");
        assertThat(layer(result, "DNS").summary()).contains("未提供");
        assertThat(layer(result, "SECURITY_GROUP").status()).isEqualTo("UNVERIFIED");
        assertThat(layer(result, "ROUTE").status()).isEqualTo("UNVERIFIED");
    }

    @Test
    void invalid_host_and_closed_runtime_are_rejected() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        StubRuntime closed = new StubRuntime(1L, false);
        String closedId = registry.register(closed);
        NetworkPathService service = new NetworkPathService(registry, new ObjectMapper());

        assertThatThrownBy(() -> service.diagnose(1L, closedId, fullRequest()))
                .isInstanceOf(BusinessException.class)
                .hasMessage("RUNTIME_CLOSED");

        assertThatThrownBy(() -> service.diagnose(1L, "missing", fullRequest()))
                .isInstanceOf(BusinessException.class)
                .hasMessage("RUNTIME_NOT_FOUND");

        StubRuntime open = new StubRuntime(1L);
        String openId = registry.register(open);
        assertThatThrownBy(() -> service.diagnose(1L, openId,
                new NetworkPathRequest(CONTEXT, NAMESPACE, "api.example.com; rm -rf /", 443,
                        SERVICE, INGRESS, "api", true, 60)))
                .isInstanceOf(BusinessException.class)
                .hasMessage("INVALID_NETWORK_PATH_PARAMETER: host");
    }

    /* ── 测试替身与夹具 ─────────────────────────────────────────────────── */

    private static NetworkPathResult diagnose(StubRuntime runtime, NetworkPathRequest request) {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        String runtimeId = registry.register(runtime);
        return new NetworkPathService(registry, new ObjectMapper())
                .diagnose(runtime.userId(), runtimeId, request);
    }

    private static NetworkLayer layer(NetworkPathResult result, String name) {
        return result.layers().stream()
                .filter(layer -> name.equals(layer.name()))
                .findFirst()
                .orElseThrow();
    }

    private static NetworkPathRequest fullRequest() {
        return new NetworkPathRequest(CONTEXT, NAMESPACE, HOST, 443, SERVICE, INGRESS, "api", true, 60);
    }

    private static StubRuntime fullPathRuntime() {
        return new StubRuntime(1L)
                .reply("getent hosts", 0, "10.0.0.10 " + HOST, "")
                .reply("get ingress", 0, """
                        {"metadata":{"name":"api-ing","namespace":"demo"},
                         "status":{"loadBalancer":{"ingress":[{"ip":"203.0.113.10"}]}}}
                        """, "")
                .reply("get svc", 0, """
                        {"metadata":{"name":"api-svc","namespace":"demo"},
                         "spec":{"type":"ClusterIP","clusterIP":"10.0.0.20","selector":{"app":"api"},
                                 "ports":[{"name":"http","port":80,"targetPort":8080,"protocol":"TCP"}]}}
                        """, "")
                .reply("get endpointslices", 0, """
                        {"items":[{"metadata":{"name":"api-svc-abc","namespace":"demo"},
                          "endpoints":[{"conditions":{"ready":true},
                                        "targetRef":{"kind":"Pod","name":"api-0"}}]}]}
                        """, "")
                .reply("get pods", 0, """
                        {"items":[{"metadata":{"name":"api-0","namespace":"demo",
                                              "labels":{"app":"api"}},
                          "status":{"phase":"Running",
                                    "conditions":[{"type":"Ready","status":"True"}]}}]}
                        """, "")
                .reply("get networkpolicy", 0, "{\"items\":[]}", "")
                .reply("openssl s_client", 0, "Verify return code: 0 (ok)", "");
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
