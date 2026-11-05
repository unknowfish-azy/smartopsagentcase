package com.smartops.diagnostics.network;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 网络链路诊断包（OPS-06）。
 *
 * <p><b>结论口径</b>：{@code OK} 只能来自“确实采到了证据且检查通过”。采集不到、没有权限、
 * 没有接入诊断接口的层一律不得写成 OK：RBAC 拒绝记为 {@code NO_PERMISSION}，对象缺失记为
 * {@code DATA_MISSING}，本仓库没有只读接口的层（安全组 / 路由）固定为 {@code UNVERIFIED}，
 * 用户没有提供的输入固定为 {@code NOT_APPLICABLE}。</p>
 *
 * <p>所有 kubectl 命令只读，带 {@code --context}/{@code -n}/{@code --request-timeout=15s}；
 * 单条命令 15s 超时，整单最多 10 条命令并受 {@code timeoutSeconds} 总预算约束。预算耗尽时
 * 置 {@code truncated=true} 并停止发起新命令，不把“没采完”当成“采完了且没问题”。</p>
 *
 * <p>上游失败会沿着链路传递：DNS 失败 → TLS 标记 {@code blockedBy=DNS}；
 * SERVICE 失败/不存在 → ENDPOINT_SLICE、POD 标记 {@code blockedBy=SERVICE}；
 * ENDPOINT_SLICE 失败 → POD 标记 {@code blockedBy=ENDPOINT_SLICE}。
 * 被阻断的层仍然继续采集并保留证据，但 summary 必须写明上游失败，其结论不可采信。</p>
 */
@Service
public class NetworkPathService {

    static final long COMMAND_TIMEOUT_MS = 15_000L;
    static final int MAX_COMMANDS = 10;
    static final int MAX_EVIDENCE_LENGTH = 300;

    private static final String LAYER_DNS = "DNS";
    private static final String LAYER_INGRESS = "INGRESS";
    private static final String LAYER_SERVICE = "SERVICE";
    private static final String LAYER_ENDPOINT_SLICE = "ENDPOINT_SLICE";
    private static final String LAYER_POD = "POD";
    private static final String LAYER_NETWORK_POLICY = "NETWORK_POLICY";
    private static final String LAYER_TLS = "TLS";
    private static final String LAYER_SECURITY_GROUP = "SECURITY_GROUP";
    private static final String LAYER_ROUTE = "ROUTE";

    static final String STATUS_OK = "OK";
    static final String STATUS_FAILED = "FAILED";
    static final String STATUS_NO_PERMISSION = "NO_PERMISSION";
    static final String STATUS_DATA_MISSING = "DATA_MISSING";
    static final String STATUS_UNVERIFIED = "UNVERIFIED";
    static final String STATUS_NOT_APPLICABLE = "NOT_APPLICABLE";
    static final String STATUS_ERROR = "ERROR";

    private static final String SECURITY_GROUP_SUMMARY =
            "未接入云安全组只读接口，需在云侧核验，不得视为通过";
    private static final String ROUTE_SUMMARY =
            "未接入云路由表只读接口，需在云侧核验，不得视为通过";

    private static final Pattern PERMISSION_ERROR =
            Pattern.compile("forbidden|unauthorized|cannot", Pattern.CASE_INSENSITIVE);
    private static final Pattern MISSING_ERROR =
            Pattern.compile("notfound|not found|no resources found", Pattern.CASE_INSENSITIVE);
    private static final Pattern UNSUPPORTED_RESOURCE = Pattern.compile(
            "doesn't have a resource type|does not have a resource type|no matches for kind"
                    + "|could not find the requested resource|not found the resource",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern COMMAND_UNAVAILABLE =
            Pattern.compile("command not found|not recognized as an internal or external command",
                    Pattern.CASE_INSENSITIVE);
    private static final Pattern VERIFY_CODE =
            Pattern.compile("Verify return code:\\s*(\\d+)\\s*\\(([^)]*)\\)");

    private static final Pattern SAFE_CONTEXT = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}");
    private static final Pattern SAFE_NAMESPACE =
            Pattern.compile("[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?");
    private static final Pattern SAFE_NAME = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");
    private static final Pattern SAFE_HOST =
            Pattern.compile("[A-Za-z0-9](?:[A-Za-z0-9._-]{0,251}[A-Za-z0-9])?");

    private final OperationRuntimeRegistry registry;
    private final ObjectMapper objectMapper;

    public NetworkPathService(OperationRuntimeRegistry registry, ObjectMapper objectMapper) {
        this.registry = registry;
        this.objectMapper = objectMapper;
    }

    public NetworkPathResult diagnose(Long userId, String runtimeId, NetworkPathRequest request) {
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        if (!runtime.isOpen()) throw new BusinessException(409, "RUNTIME_CLOSED");
        validate(request);

        Instant startedAt = Instant.now();
        Run run = new Run(runtime, request, startedAt);
        List<NetworkLayer> layers = new ArrayList<>(9);

        NetworkLayer dns = collectDns(run);
        layers.add(dns);

        NetworkLayer ingress = collectIngress(run);
        layers.add(ingress);

        NetworkLayer service = collectService(run);
        layers.add(service);
        boolean serviceBlocked = blocksDownstream(service, request.service());

        NetworkLayer endpointSlice = collectEndpointSlices(run, serviceBlocked ? LAYER_SERVICE : null);
        layers.add(endpointSlice);
        boolean endpointBlocked = STATUS_FAILED.equals(endpointSlice.status());

        String podBlockedBy = serviceBlocked ? LAYER_SERVICE
                : (endpointBlocked ? LAYER_ENDPOINT_SLICE : null);
        layers.add(collectPods(run, podBlockedBy));

        layers.add(collectNetworkPolicies(run));

        layers.add(collectTls(run, STATUS_FAILED.equals(dns.status()) ? LAYER_DNS : null));

        layers.add(unverifiedLayer(LAYER_SECURITY_GROUP, SECURITY_GROUP_SUMMARY));
        layers.add(unverifiedLayer(LAYER_ROUTE, ROUTE_SUMMARY));

        Instant endedAt = Instant.now();
        boolean permissionDenied = layers.stream()
                .anyMatch(layer -> STATUS_NO_PERMISSION.equals(layer.status()));
        boolean dataMissing = layers.stream()
                .anyMatch(layer -> STATUS_DATA_MISSING.equals(layer.status()));
        boolean unverified = layers.stream()
                .anyMatch(layer -> STATUS_UNVERIFIED.equals(layer.status()));
        NetworkScope scope = new NetworkScope(request.context(), request.namespace(), request.host(),
                request.port(), request.service(), request.ingress(), request.workload(), request.tls(),
                request.timeoutSeconds());
        return new NetworkPathResult(scope, startedAt.toString(), endedAt.toString(),
                Duration.between(startedAt, endedAt).toMillis(), List.copyOf(layers),
                permissionDenied, dataMissing, unverified, run.truncated);
    }

    /* ── 采集各层 ───────────────────────────────────────────────────────── */

    private NetworkLayer collectDns(Run run) {
        NetworkPathRequest request = run.request;
        if (request.host() == null) {
            return notApplicable(LAYER_DNS, "未提供 host，未核验 DNS 解析");
        }
        String command = "getent hosts " + request.host();
        Execution execution = run.execute(command);
        if (execution == null) return budgetExhausted(LAYER_DNS, command, null);

        String combined = (execution.stdout() + " " + execution.stderr()).trim();
        if (COMMAND_UNAVAILABLE.matcher(combined).find()) {
            return unverifiedLayer(LAYER_DNS, "目标主机无法执行 getent（command not found），DNS 未核验",
                    check(LAYER_DNS, STATUS_UNVERIFIED, command,
                            "exit=" + execution.exitCode() + " output=" + combined,
                            execution.collectedAt(), 0));
        }
        if (containsIgnoreCase(combined, "nxdomain") || containsIgnoreCase(combined, "not known")
                || execution.exitCode() != 0) {
            return layer(LAYER_DNS, STATUS_FAILED, "DNS 解析失败，主机名无法解析", null,
                    List.of(check(LAYER_DNS, STATUS_FAILED, command,
                            "exit=" + execution.exitCode() + " output=" + combined,
                            execution.collectedAt(), 0)));
        }
        if (execution.stdout().isBlank()) {
            return layer(LAYER_DNS, STATUS_DATA_MISSING, "getent 返回成功但没有解析结果，DNS 未核验", null,
                    List.of(check(LAYER_DNS, STATUS_DATA_MISSING, command,
                            "exit=0 but output is empty", execution.collectedAt(), 0)));
        }
        int resolved = (int) execution.stdout().lines().filter(line -> !line.isBlank()).count();
        return layer(LAYER_DNS, STATUS_OK, "DNS 解析成功，共 " + resolved + " 条记录", null,
                List.of(check(LAYER_DNS, STATUS_OK, command, combined, execution.collectedAt(), resolved)));
    }

    private NetworkLayer collectIngress(Run run) {
        NetworkPathRequest request = run.request;
        if (request.ingress() == null) {
            return notApplicable(LAYER_INGRESS, "未提供 ingress，未核验 Ingress");
        }
        String command = kubectl(request, "get ingress " + request.ingress());
        Execution execution = run.execute(command);
        if (execution == null) return budgetExhausted(LAYER_INGRESS, command, null);
        if (execution.exitCode() != 0) {
            return failedFromCommand(LAYER_INGRESS, command, execution, null, "kubectl get ingress");
        }
        JsonNode root = readJson(execution);
        JsonNode ingress = root == null ? null : singleObject(root);
        if (ingress == null) {
            return layer(LAYER_INGRESS, STATUS_DATA_MISSING, "未取到 Ingress 对象，未核验入口", null,
                    List.of(check(LAYER_INGRESS, STATUS_DATA_MISSING, command,
                            "ingress not present in output", execution.collectedAt(), 0)));
        }

        JsonNode addresses = ingress.path("status").path("loadBalancer").path("ingress");
        List<String> values = new ArrayList<>();
        if (addresses.isArray()) {
            for (JsonNode address : addresses) {
                String value = address.path("ip").asText("");
                if (value.isBlank()) value = address.path("hostname").asText("");
                if (!value.isBlank()) values.add(value);
            }
        }
        if (values.isEmpty()) {
            return layer(LAYER_INGRESS, STATUS_FAILED,
                    "Ingress 未下发负载均衡地址（status.loadBalancer.ingress 为空）", null,
                    List.of(check(LAYER_INGRESS, STATUS_FAILED, command,
                            "status.loadBalancer.ingress is empty", execution.collectedAt(), 0)));
        }
        return layer(LAYER_INGRESS, STATUS_OK, "Ingress 已下发 " + values.size() + " 个负载均衡地址", null,
                List.of(check(LAYER_INGRESS, STATUS_OK, command,
                        "loadBalancer=" + String.join(",", values), execution.collectedAt(), values.size())));
    }

    private NetworkLayer collectService(Run run) {
        NetworkPathRequest request = run.request;
        if (request.service() == null) {
            return notApplicable(LAYER_SERVICE, "未提供 service，未核验 Service");
        }
        String command = kubectl(request, "get svc " + request.service());
        Execution execution = run.execute(command);
        if (execution == null) return budgetExhausted(LAYER_SERVICE, command, null);
        if (execution.exitCode() != 0) {
            return failedFromCommand(LAYER_SERVICE, command, execution, null, "kubectl get svc");
        }
        JsonNode root = readJson(execution);
        JsonNode service = root == null ? null : singleObject(root);
        if (service == null) {
            return layer(LAYER_SERVICE, STATUS_DATA_MISSING, "未取到 Service 对象，未核验 Service", null,
                    List.of(check(LAYER_SERVICE, STATUS_DATA_MISSING, command,
                            "service not present in output", execution.collectedAt(), 0)));
        }

        String type = textAt(service, "spec", "type");
        String clusterIp = textAt(service, "spec", "clusterIP");
        String ports = describePorts(service);
        JsonNode selector = service.path("spec").path("selector");
        String evidence = "type=" + type + " clusterIP=" + clusterIp
                + " ports=" + ports + " selector=" + describeFields(selector);
        if (!selector.isObject() || selector.isEmpty()) {
            return layer(LAYER_SERVICE, STATUS_FAILED,
                    "Service 没有 spec.selector，不会有 EndpointSlice 指向它", null,
                    List.of(check(LAYER_SERVICE, STATUS_FAILED, command,
                            "type=" + type + " clusterIP=" + clusterIp + " ports=" + ports
                                    + " selector=empty",
                            execution.collectedAt(), 0)));
        }
        return layer(LAYER_SERVICE, STATUS_OK,
                "Service 类型 " + type + "，clusterIP " + clusterIp + "，selector "
                        + describeFields(selector), null,
                List.of(check(LAYER_SERVICE, STATUS_OK, command, evidence, execution.collectedAt(), 1)));
    }

    private NetworkLayer collectEndpointSlices(Run run, String blockedBy) {
        NetworkPathRequest request = run.request;
        if (request.service() == null) {
            return notApplicable(LAYER_ENDPOINT_SLICE, "未提供 service，未核验 EndpointSlice");
        }
        String command = kubectl(request,
                "get endpointslices -l kubernetes.io/service-name=" + request.service());
        Execution execution = run.execute(command);
        if (execution == null) return budgetExhausted(LAYER_ENDPOINT_SLICE, command, blockedBy);
        if (execution.exitCode() != 0) {
            return failedFromCommand(LAYER_ENDPOINT_SLICE, command, execution, blockedBy,
                    "kubectl get endpointslices");
        }
        JsonNode root = readJson(execution);
        if (root == null) {
            return layer(LAYER_ENDPOINT_SLICE, STATUS_ERROR, "EndpointSlice 输出不是有效 JSON，本层未核验",
                    blockedBy, List.of(check(LAYER_ENDPOINT_SLICE, STATUS_ERROR, command,
                            "endpointslices output is not valid JSON", execution.collectedAt(), 0)));
        }

        int itemCount = 0;
        int readyCount = 0;
        int notReadyCount = 0;
        List<String> notReadyEvidence = new ArrayList<>();
        for (JsonNode slice : root.path("items")) {
            itemCount++;
            for (JsonNode endpoint : slice.path("endpoints")) {
                JsonNode ready = endpoint.path("conditions").path("ready");
                String pod = textAt(endpoint, "targetRef", "name");
                if (ready.isBoolean() && ready.asBoolean()) {
                    readyCount++;
                } else {
                    notReadyCount++;
                    notReadyEvidence.add("endpoint pod=" + (pod.isBlank() ? "unknown" : pod)
                            + " slice=" + textAt(slice, "metadata", "name")
                            + " ready=" + (ready.isMissingNode() ? "unknown" : ready.asText("false")));
                }
            }
        }

        String status;
        String summary;
        if (itemCount == 0) {
            status = STATUS_FAILED;
            summary = "未发现该 Service 的 EndpointSlice，ready 端点数为 0";
        } else if (readyCount == 0) {
            status = STATUS_FAILED;
            summary = "EndpointSlice 中 ready 端点数为 0（notReady=" + notReadyCount + "）";
        } else if (notReadyCount > 0) {
            status = STATUS_UNVERIFIED;
            summary = "ready=" + readyCount + " notReady=" + notReadyCount + "，部分端点未 Ready，需人工确认";
        } else {
            status = STATUS_OK;
            summary = "EndpointSlice ready 端点数为 " + readyCount;
        }

        List<NetworkCheck> checks = new ArrayList<>();
        checks.add(check(LAYER_ENDPOINT_SLICE, status, command,
                "slices=" + itemCount + " ready=" + readyCount + " notReady=" + notReadyCount,
                execution.collectedAt(), readyCount));
        for (String evidence : notReadyEvidence) {
            checks.add(check("ENDPOINT_NOT_READY", status, command, evidence, execution.collectedAt(), 1));
        }
        return layer(LAYER_ENDPOINT_SLICE, status, summary, blockedBy, checks);
    }

    private NetworkLayer collectPods(Run run, String blockedBy) {
        NetworkPathRequest request = run.request;
        String command = kubectl(request, "get pods"
                + (request.workload() == null ? "" : " -l app=" + request.workload()));
        Execution execution = run.execute(command);
        if (execution == null) return budgetExhausted(LAYER_POD, command, blockedBy);
        if (execution.exitCode() != 0) {
            return failedFromCommand(LAYER_POD, command, execution, blockedBy, "kubectl get pods");
        }
        JsonNode root = readJson(execution);
        if (root == null) {
            return layer(LAYER_POD, STATUS_ERROR, "Pod 输出不是有效 JSON，本层未核验", blockedBy,
                    List.of(check(LAYER_POD, STATUS_ERROR, command,
                            "pods output is not valid JSON", execution.collectedAt(), 0)));
        }

        int itemCount = 0;
        int notReadyCount = 0;
        List<String> notReadyEvidence = new ArrayList<>();
        for (JsonNode pod : root.path("items")) {
            itemCount++;
            run.podLabels.add(pod.path("metadata").path("labels"));
            String podName = textAt(pod, "metadata", "name");
            String phase = textAt(pod, "status", "phase");
            String readyValue = "unknown";
            for (JsonNode condition : pod.path("status").path("conditions")) {
                if ("Ready".equals(textAt(condition, "type"))) {
                    readyValue = textAt(condition, "status");
                }
            }
            if (!"True".equals(readyValue)) {
                notReadyCount++;
                notReadyEvidence.add("pod=" + podName + " phase=" + (phase.isBlank() ? "unknown" : phase)
                        + " Ready=" + readyValue);
            }
        }

        String status;
        String summary;
        if (itemCount == 0) {
            status = STATUS_DATA_MISSING;
            summary = "未取到符合筛选条件的 Pod，无法核验后端就绪状态";
        } else if (notReadyCount == itemCount) {
            status = STATUS_FAILED;
            summary = "全部 " + itemCount + " 个 Pod 未 Ready";
        } else if (notReadyCount > 0) {
            status = STATUS_UNVERIFIED;
            summary = itemCount + " 个 Pod 中 " + notReadyCount + " 个未 Ready，需人工确认";
        } else {
            status = STATUS_OK;
            summary = itemCount + " 个 Pod 全部 Ready";
        }

        List<NetworkCheck> checks = new ArrayList<>();
        checks.add(check(LAYER_POD, status, command,
                "pods=" + itemCount + " notReady=" + notReadyCount, execution.collectedAt(), itemCount));
        for (String evidence : notReadyEvidence) {
            checks.add(check("POD_NOT_READY", status, command, evidence, execution.collectedAt(), 1));
        }
        return layer(LAYER_POD, status, summary, blockedBy, checks);
    }

    private NetworkLayer collectNetworkPolicies(Run run) {
        NetworkPathRequest request = run.request;
        String command = kubectl(request, "get networkpolicy");
        Execution execution = run.execute(command);
        if (execution == null) return budgetExhausted(LAYER_NETWORK_POLICY, command, null);

        String message = execution.stderr().isBlank() ? execution.stdout() : execution.stderr();
        if (execution.exitCode() != 0) {
            if (UNSUPPORTED_RESOURCE.matcher(message).find()) {
                return notApplicable(LAYER_NETWORK_POLICY,
                        "集群未提供 networkpolicy 资源类型，本层不适用");
            }
            return failedFromCommand(LAYER_NETWORK_POLICY, command, execution, null,
                    "kubectl get networkpolicy");
        }
        JsonNode root = readJson(execution);
        if (root == null) {
            return layer(LAYER_NETWORK_POLICY, STATUS_ERROR, "NetworkPolicy 输出不是有效 JSON，本层未核验",
                    null, List.of(check(LAYER_NETWORK_POLICY, STATUS_ERROR, command,
                            "networkpolicy output is not valid JSON", execution.collectedAt(), 0)));
        }

        int itemCount = 0;
        List<String> matched = new ArrayList<>();
        List<NetworkCheck> checks = new ArrayList<>();
        for (JsonNode policy : root.path("items")) {
            itemCount++;
            if (!matchesPods(policy, run.podLabels)) continue;
            String policyName = textAt(policy, "metadata", "name");
            matched.add(policyName);
            checks.add(check("NETWORK_POLICY_MATCH", STATUS_OK, command,
                    "policy=" + policyName + " podSelector.matchLabels="
                            + describeFields(policy.path("spec").path("podSelector").path("matchLabels")),
                    execution.collectedAt(), 1));
        }

        if (matched.isEmpty()) {
            checks.add(0, check(LAYER_NETWORK_POLICY, STATUS_OK, command,
                    "networkPolicies=" + itemCount + " matched=0", execution.collectedAt(), 0));
            return layer(LAYER_NETWORK_POLICY, STATUS_OK,
                    "未发现作用于这些 Pod 的 NetworkPolicy（共 " + itemCount + " 个策略）", null, checks);
        }
        checks.add(0, check(LAYER_NETWORK_POLICY, STATUS_OK, command,
                "networkPolicies=" + itemCount + " matched=" + matched.size()
                        + " names=" + String.join(",", matched),
                execution.collectedAt(), matched.size()));
        return layer(LAYER_NETWORK_POLICY, STATUS_OK,
                "存在 " + matched.size() + " 个作用于这些 Pod 的 NetworkPolicy（"
                        + String.join(",", matched) + "），需人工确认规则是否放行", null, checks);
    }

    private NetworkLayer collectTls(Run run, String blockedBy) {
        NetworkPathRequest request = run.request;
        if (!request.tls() || request.host() == null) {
            return notApplicable(LAYER_TLS, "未启用 TLS 或未提供 host，未核验 TLS 握手");
        }
        String command = "openssl s_client -connect " + request.host() + ":" + request.port()
                + " -servername " + request.host() + " -verify_return_error < /dev/null";
        Execution execution = run.execute(command);
        if (execution == null) return budgetExhausted(LAYER_TLS, command, blockedBy);

        String combined = execution.stdout() + "\n" + execution.stderr();
        if (COMMAND_UNAVAILABLE.matcher(combined).find()) {
            return unverifiedLayer(LAYER_TLS, "目标主机无法执行 openssl（command not found），TLS 未核验",
                    check(LAYER_TLS, STATUS_UNVERIFIED, command,
                            "openssl not available", execution.collectedAt(), 0));
        }
        Matcher matcher = VERIFY_CODE.matcher(combined);
        if (!matcher.find()) {
            return layer(LAYER_TLS, STATUS_ERROR, "openssl 未输出 Verify return code，TLS 未核验", blockedBy,
                    List.of(check(LAYER_TLS, STATUS_ERROR, command,
                            "no verify return code, exit=" + execution.exitCode()
                                    + " output=" + brief(combined),
                            execution.collectedAt(), 0)));
        }
        String code = matcher.group(1);
        String reason = matcher.group(2).trim();
        if ("0".equals(code)) {
            return layer(LAYER_TLS, STATUS_OK, "TLS 证书校验通过（Verify return code: 0）", blockedBy,
                    List.of(check(LAYER_TLS, STATUS_OK, command,
                            "Verify return code: 0 (" + reason + ")", execution.collectedAt(), 1)));
        }
        return layer(LAYER_TLS, STATUS_FAILED,
                "TLS 证书校验失败：Verify return code " + code, blockedBy,
                List.of(check(LAYER_TLS, STATUS_FAILED, command,
                        "Verify return code: " + code + " (" + reason + ")", execution.collectedAt(), 0)));
    }

    /* ── 层与检查项构造 ─────────────────────────────────────────────────── */

    private static NetworkLayer layer(String name, String status, String summary, String blockedBy,
                                      List<NetworkCheck> checks) {
        String effectiveSummary = blockedBy == null ? summary
                : "上游 " + blockedBy + " 未通过，本层结果不可采信：" + summary;
        String collectedAt = checks.isEmpty()
                ? Instant.now().toString()
                : checks.get(checks.size() - 1).collectedAt();
        return new NetworkLayer(name, status, effectiveSummary, List.copyOf(checks), blockedBy, collectedAt);
    }

    private static NetworkLayer notApplicable(String name, String summary) {
        return layer(name, STATUS_NOT_APPLICABLE, summary, null,
                List.of(check(name, STATUS_NOT_APPLICABLE, "", "not applicable", Instant.now(), 0)));
    }

    private static NetworkLayer unverifiedLayer(String name, String summary) {
        return unverifiedLayer(name, summary,
                check(name, STATUS_UNVERIFIED, "", summary, Instant.now(), 0));
    }

    private static NetworkLayer unverifiedLayer(String name, String summary, NetworkCheck check) {
        return layer(name, STATUS_UNVERIFIED, summary, null, List.of(check));
    }

    private static NetworkLayer budgetExhausted(String name, String command, String blockedBy) {
        return layer(name, STATUS_ERROR, "命令预算或整单总超时已耗尽，本层未采集", blockedBy,
                List.of(check(name, STATUS_ERROR, command,
                        "command budget exhausted before collection", Instant.now(), 0)));
    }

    private static NetworkLayer failedFromCommand(String name, String command, Execution execution,
                                                  String blockedBy, String what) {
        String status = failureStatus(execution);
        String message = execution.stderr().isBlank() ? execution.stdout() : execution.stderr();
        String summary = switch (status) {
            case STATUS_NO_PERMISSION -> what + " 被拒绝（RBAC/认证），本层未核验";
            case STATUS_DATA_MISSING -> what + " 未找到目标对象，本层未核验";
            default -> what + " 执行失败，本层未核验";
        };
        return layer(name, status, summary, blockedBy,
                List.of(check(name, status, command, message, execution.collectedAt(), 0)));
    }

    private static NetworkCheck check(String name, String status, String command, String evidence,
                                      Instant collectedAt, int itemCount) {
        return new NetworkCheck(name, status, command, brief(evidence), collectedAt.toString(), itemCount);
    }

    private static boolean blocksDownstream(NetworkLayer service, String requestedService) {
        if (requestedService == null) return false;
        return !STATUS_OK.equals(service.status());
    }

    /* ── 判定与解析辅助 ─────────────────────────────────────────────────── */

    private static String failureStatus(Execution execution) {
        String message = execution.stderr().isBlank() ? execution.stdout() : execution.stderr();
        if (PERMISSION_ERROR.matcher(message).find()) return STATUS_NO_PERMISSION;
        if (MISSING_ERROR.matcher(message).find()) return STATUS_DATA_MISSING;
        return STATUS_ERROR;
    }

    private JsonNode readJson(Execution execution) {
        if (execution.stdout().isBlank()) return null;
        try {
            return objectMapper.readTree(execution.stdout());
        } catch (JsonProcessingException ex) {
            return null;
        }
    }

    private static JsonNode singleObject(JsonNode root) {
        JsonNode items = root.path("items");
        if (items.isArray()) return items.isEmpty() ? null : items.get(0);
        return root.has("metadata") ? root : null;
    }

    private static boolean matchesPods(JsonNode policy, List<JsonNode> podLabels) {
        JsonNode selector = policy.path("spec").path("podSelector").path("matchLabels");
        if (!selector.isObject() || selector.isEmpty()) return true;
        for (JsonNode labels : podLabels) {
            boolean all = true;
            var fields = selector.fields();
            while (fields.hasNext()) {
                var entry = fields.next();
                if (!entry.getValue().asText("").equals(labels.path(entry.getKey()).asText(""))) {
                    all = false;
                    break;
                }
            }
            if (all) return true;
        }
        return false;
    }

    private static String describePorts(JsonNode service) {
        List<String> ports = new ArrayList<>();
        for (JsonNode port : service.path("spec").path("ports")) {
            StringBuilder builder = new StringBuilder();
            String name = textAt(port, "name");
            if (!name.isBlank()) builder.append(name).append(':');
            builder.append(port.path("port").asInt(0)).append("->").append(port.path("targetPort").asText(""));
            String protocol = textAt(port, "protocol");
            if (!protocol.isBlank()) builder.append('/').append(protocol);
            ports.add(builder.toString());
        }
        return ports.isEmpty() ? "none" : String.join(",", ports);
    }

    private static String describeFields(JsonNode node) {
        if (node == null || !node.isObject() || node.isEmpty()) return "empty";
        List<String> values = new ArrayList<>();
        var fields = node.fields();
        while (fields.hasNext()) {
            var entry = fields.next();
            values.add(entry.getKey() + "=" + entry.getValue().asText(""));
        }
        return String.join(",", values);
    }

    private static boolean containsIgnoreCase(String value, String needle) {
        return value != null && value.toLowerCase(Locale.ROOT).contains(needle.toLowerCase(Locale.ROOT));
    }

    private static String textAt(JsonNode node, String... path) {
        JsonNode current = node;
        for (String segment : path) {
            if (current == null) return "";
            current = current.path(segment);
        }
        if (current == null || current.isMissingNode() || current.isNull()) return "";
        return current.asText("");
    }

    private static String brief(String value) {
        if (value == null) return "";
        String singleLine = value.replace('\n', ' ').replace('\r', ' ').replaceAll("\\s+", " ").trim();
        return singleLine.length() <= MAX_EVIDENCE_LENGTH
                ? singleLine
                : singleLine.substring(0, MAX_EVIDENCE_LENGTH) + "...";
    }

    private static String text(String value) {
        return value == null ? "" : value;
    }

    private static String kubectl(NetworkPathRequest request, String args) {
        return "kubectl " + args + " --context " + request.context()
                + " -n " + request.namespace() + " --request-timeout=15s -o json";
    }

    private static void validate(NetworkPathRequest request) {
        if (!SAFE_CONTEXT.matcher(text(request.context())).matches()) invalid("context");
        if (!SAFE_NAMESPACE.matcher(text(request.namespace())).matches()) invalid("namespace");
        validateOptionalName(request.service(), "service");
        validateOptionalName(request.ingress(), "ingress");
        validateOptionalName(request.workload(), "workload");
        if (request.host() != null && !SAFE_HOST.matcher(request.host()).matches()) invalid("host");
        if (request.port() > 65535) invalid("port");
    }

    private static void validateOptionalName(String value, String field) {
        if (value != null && !SAFE_NAME.matcher(value).matches()) invalid(field);
    }

    private static void invalid(String field) {
        throw new BusinessException(400, "INVALID_NETWORK_PATH_PARAMETER: " + field);
    }

    /* ── 对外模型 ───────────────────────────────────────────────────────── */

    public record NetworkScope(String context, String namespace, String host, int port, String service,
                               String ingress, String workload, boolean tls, int timeoutSeconds) {}

    public record NetworkCheck(String name, String status, String command, String evidence,
                               String collectedAt, int itemCount) {}

    public record NetworkLayer(String name, String status, String summary, List<NetworkCheck> checks,
                               String blockedBy, String collectedAt) {}

    public record NetworkPathResult(NetworkScope scope, String startedAt, String endedAt, long durationMs,
                                    List<NetworkLayer> layers, boolean permissionDenied, boolean dataMissing,
                                    boolean unverified, boolean truncated) {}

    /* ── 内部运行态 ─────────────────────────────────────────────────────── */

    private record Execution(String command, int exitCode, String stdout, String stderr, Instant collectedAt) {}

    private static final class Run {
        private final OperationRuntime runtime;
        private final NetworkPathRequest request;
        private final Instant startedAt;
        private final Instant deadline;
        private final List<JsonNode> podLabels = new ArrayList<>();
        private int commandsUsed;
        private boolean truncated;

        private Run(OperationRuntime runtime, NetworkPathRequest request, Instant startedAt) {
            this.runtime = runtime;
            this.request = request;
            this.startedAt = startedAt;
            this.deadline = startedAt.plusSeconds(request.timeoutSeconds());
        }

        private Execution execute(String command) {
            if (commandsUsed >= MAX_COMMANDS || Instant.now().isAfter(deadline)) {
                truncated = true;
                return null;
            }
            commandsUsed++;
            try {
                OperationRuntime.CommandResult result = runtime.execute(command, COMMAND_TIMEOUT_MS);
                return new Execution(command, result.exitCode(), text(result.stdout()), text(result.stderr()),
                        Instant.now());
            } catch (IOException ex) {
                String message = ex.getMessage();
                return new Execution(command, -1, "",
                        message == null || message.isBlank() ? "COMMAND_EXECUTION_FAILED" : message,
                        Instant.now());
            }
        }
    }
}
