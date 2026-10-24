package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;

import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.regex.Pattern;

@Service
public class OperationToolService {
    private static final long COMMAND_TIMEOUT_MS = 30_000;
    private static final Pattern SAFE_NAME = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");
    private static final Pattern SAFE_NAMESPACE = Pattern.compile("[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?");
    private static final Pattern POSITIVE_INTEGER = Pattern.compile("[1-9][0-9]{0,5}");
    private static final Pattern SAFE_SEARCH = Pattern.compile("[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,127}");

    private final OperationRuntimeRegistry registry;
    private final OperationRunRecorder runRecorder;
    private final Map<String, ToolDefinition> tools;
    private final ObservabilityService observability;

    public OperationToolService(OperationRuntimeRegistry registry) {
        this(registry, new NoOpRunRecorder());
    }

    public OperationToolService(OperationRuntimeRegistry registry, OperationRunRecorder runRecorder) {
        this(registry, runRecorder, null);
    }

    @Autowired
    public OperationToolService(OperationRuntimeRegistry registry, OperationRunRecorder runRecorder, ObservabilityService observability) {
        this.registry = registry;
        this.runRecorder = runRecorder;
        this.observability = observability;
        this.tools = Map.ofEntries(
                Map.entry("docker-compose-status", readOnly("docker-compose-status", ignored -> List.of("docker compose ls --all --format json"))),
                Map.entry("helm-releases", readOnly("helm-releases", values -> List.of(
                        "helm list -n " + safeNamespace(values, "namespace", "default") + " --max 100 -o json"))),
                Map.entry("k8s-storage", readOnly("k8s-storage", values -> List.of(
                        "kubectl get pvc -n " + safeNamespace(values, "namespace", "default") + " -o wide",
                        "kubectl get storageclass"))),
                Map.entry("k8s-rbac-check", readOnly("k8s-rbac-check", values -> List.of(
                        "kubectl auth can-i get pods -n " + safeNamespace(values, "namespace", "default"),
                        "kubectl auth can-i get pods --subresource=log -n " + safeNamespace(values, "namespace", "default")))),
                Map.entry("mesh-status", readOnly("mesh-status", values -> List.of(
                        "kubectl get pods,services -n " + safeNamespace(values, "namespace", "istio-system") + " -o wide"))),
                Map.entry("terraform-environment", readOnly("terraform-environment", ignored -> List.of("terraform version -json"))),
                Map.entry("harbor-endpoint-check", readOnly("harbor-endpoint-check", values -> List.of(
                        "curl --fail --silent --show-error --max-time 10 https://" + safeHost(values, "host") + "/api/v2.0/health"))),
                Map.entry("containerd-registry-inspect", readOnly("containerd-registry-inspect", values -> List.of(
                        "ctr namespaces list", "ctr -n " + safeNamespace(values, "namespace", "k8s.io") + " images list",
                        "ctr plugins ls"))),
                Map.entry("containerd-config-check", readOnly("containerd-config-check", ignored -> List.of(
                        "containerd config dump", "find /etc/containerd/certs.d -maxdepth 3 -name hosts.toml -print"))),
                Map.entry("host-health", readOnly("host-health", ignored -> List.of(
                        "uptime", "free -h", "df -hT", "ss -lntup"))),
                Map.entry("system-logs", readOnly("system-logs", values -> List.of(
                        "journalctl -p " + choice(values, "priority", "warning", List.of("emerg", "alert", "crit", "err", "warning", "notice", "info"))
                                + " -n " + positiveInteger(values, "lines", "200") + " --no-pager"))),
                Map.entry("docker-containers", readOnly("docker-containers", ignored -> List.of(
                        "docker ps --no-trunc", "docker stats --no-stream"))),
                Map.entry("docker-logs", readOnly("docker-logs", values -> List.of(
                        "docker logs --tail " + positiveInteger(values, "tail", "200") + " " + safeName(values, "container")))),
                Map.entry("k8s-resources", readOnly("k8s-resources", OperationToolService::kubernetesResourceCommands)),
                Map.entry("k8s-logs", readOnly("k8s-logs", values -> {
                    String namespace = safeNamespace(values, "namespace", "default");
                    String pod = safeName(values, "pod");
                    String container = optionalSafeName(values, "container");
                    String suffix = container.isBlank() ? "" : " -c " + container;
                    return List.of("kubectl logs " + pod + suffix + " -n " + namespace + " --tail="
                            + positiveInteger(values, "tail", "200"));
                })),
                Map.entry("log-search", readOnly("log-search", values -> List.of(
                        "journalctl -u " + safeName(values, "service") + " -n " + positiveInteger(values, "lines", "200") + " --no-pager | grep -i -- '" + safeSearch(values, "keyword") + "'"))),
                Map.entry("network-diagnostics", readOnly("network-diagnostics", values -> List.of(
                        "ping -c 3 " + safeName(values, "host"),
                        "nc -vz -w 5 " + safeName(values, "host") + " " + positiveInteger(values, "port", "443"),
                        "dig " + safeName(values, "host")))),
                Map.entry("alerts-query", readOnly("alerts-query", ignored -> List.of(
                        "curl --fail --silent http://alertmanager:9093/api/v2/alerts"))),
                Map.entry("knowledge-retrieval", readOnly("knowledge-retrieval", values -> List.of(
                        "smartops knowledge search --query '" + safeSearch(values, "keyword") + "' --top-k " + positiveInteger(values, "topK", "5")))),
                Map.entry("database-readonly", readOnly("database-readonly", values -> List.of(
                        "smartops db inspect --metric " + safeName(values, "metric") + " --read-only"))),
                Map.entry("prometheus-query", readOnly("prometheus-query", values -> List.of(
                        "HTTP GET configured Prometheus /api/v1/query_range (read-only)"))),
                Map.entry("grafana-dashboard", readOnly("grafana-dashboard", values -> List.of(
                        "smartops grafana panel --dashboard " + safeName(values, "dashboard") + " --panel " + safeName(values, "panel") + " --read-only"))),
                Map.entry("loki-log-query", readOnly("loki-log-query", values -> List.of(
                        "HTTP GET configured Loki /loki/api/v1/query_range (read-only)"))),
                Map.entry("mysql-slow-query", readOnly("mysql-slow-query", values -> List.of(
                        "smartops db slow-queries --database " + safeName(values, "database") + " --limit " + positiveInteger(values, "limit", "20") + " --read-only"))),
                Map.entry("k8s-diagnose", readOnly("k8s-diagnose", values -> {
                    String namespace = safeNamespace(values, "namespace", "default");
                    String name = safeName(values, "name");
                    return List.of(
                            "kubectl get pod,deploy,svc,endpoints -n " + namespace + " -l app=" + name + " -o wide",
                            "kubectl get events -n " + namespace + " --sort-by=.lastTimestamp");
                })),
                Map.entry("alerts-suppress", new ToolDefinition("alerts-suppress", false, values -> List.of(
                        "# approval required before creating alert silence for " + safeName(values, "alert")), "ALERT_SUPPRESS")),
                /*
                 * 告警联动处置的受控入口（协作优化 4）。
                 *
                 * 刻意声明为非只读：TeamAgentRun 因此进入 PENDING_APPROVAL，
                 * 必须经预览 + 审批 + 一次性授权才能执行，与其它变更类工具同一条链。
                 *
                 * 它本身不渲染任何 shell 命令：真正的命令来自哨兵脚本库，
                 * 由 SentinelScriptRunner 生成 MultiExec 预览后交给人确认。
                 * 放在这里的意义是"让团队 Agent 有资格提出处置"，而不是"让它自己执行"。
                 */
                Map.entry("propose-remediation", new ToolDefinition("propose-remediation", false,
                        values -> List.of("# 提交哨兵处置建议：告警 " + safeName(values, "alertId")
                                + " / 脚本 " + safeName(values, "scriptId")
                                + " —— 需生成预览并人工审批后执行"), "SENTINEL_REMEDIATION")),
                Map.entry("service-restart", new ToolDefinition("service-restart", false, values ->
                        List.of("systemctl restart " + safeName(values, "service")), "SERVICE_RESTART"))
        );
    }

    public ToolPreview preview(Long userId, String toolId, Map<String, String> parameters) {
        ToolDefinition tool = requireTool(toolId);
        return new ToolPreview(tool.id(), tool.readOnly(), List.copyOf(tool.renderer().apply(safeMap(parameters))));
    }

    public List<ToolDescriptor> listTools() {
        return tools.values().stream()
                .map(tool -> new ToolDescriptor(tool.id(), tool.readOnly(), tool.readOnly() ? "LOW" : "HIGH",
                        !tool.readOnly(), tool.capability()))
                .sorted(java.util.Comparator.comparing(ToolDescriptor::toolId))
                .toList();
    }

    public ToolRunResult execute(Long userId, String runtimeId, String toolId, Map<String, String> parameters) {
        return executeInternal(userId, runtimeId, toolId, parameters, false);
    }

    public ToolRunResult executeApprovedTeamRun(Long userId, String runtimeId, String toolId, Map<String, String> parameters) {
        if ("alerts-suppress".equals(toolId)) throw new BusinessException(501, "TEAM_TOOL_NOT_IMPLEMENTED");
        // propose-remediation 是"提议"而非"执行"：它必须经 SentinelScriptRunner 生成
        // MultiExec 预览后由人确认，不允许从这个通用执行入口直接跑掉。
        if ("propose-remediation".equals(toolId)) {
            throw new BusinessException(409, "TEAM_REMEDIATION_REQUIRES_SENTINEL_PREVIEW");
        }
        return executeInternal(userId, runtimeId, toolId, parameters, true);
    }

    private ToolRunResult executeInternal(Long userId, String runtimeId, String toolId, Map<String, String> parameters, boolean approvedTeamRun) {
        ToolDefinition tool = requireTool(toolId);
        if (!tool.readOnly() && !approvedTeamRun) throw new BusinessException(409, "TOOL_CONFIRMATION_REQUIRED");
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        if (!runtime.isOpen()) throw new BusinessException(409, "RUNTIME_CLOSED");

        if (toolId.equals("prometheus-query") || toolId.equals("loki-log-query")) {
            if (observability == null) throw new BusinessException(503, "OBSERVABILITY_NOT_CONFIGURED");
            Map<String, String> values = safeMap(parameters);
            boolean prometheus = toolId.equals("prometheus-query");
            Instant started = Instant.now();
            var response = observability.query(userId, prometheus ? "prometheus" : "loki",
                    values.getOrDefault(prometheus ? "query" : "selector", prometheus ? "up" : "{app=\"api\"}"),
                    Integer.parseInt(positiveInteger(values, "range", "15")),
                    Integer.parseInt(positiveInteger(values, "lines", "200")));
            Instant finished = Instant.now();
            return new ToolRunResult(response.traceId(), runtimeId, toolId, "SUCCEEDED", List.of(
                    new ToolCommandResult("HTTP " + response.source() + " read-only query", 0,
                            response.response().toString(), "", started, finished)), started, finished);
        }

        ToolPreview preview = preview(userId, toolId, parameters);
        Instant startedAt = Instant.now();
        String traceId = UUID.randomUUID().toString();
        OperationRunRecorder.RunHandle run = runRecorder.start(traceId, userId, runtime, toolId, startedAt);
        List<ToolCommandResult> results = new ArrayList<>();
        String status = "SUCCEEDED";
        int sequence = 0;
        for (String command : preview.commands()) {
            sequence++;
            Instant commandStartedAt = Instant.now();
            try {
                OperationRuntime.CommandResult result = runtime.execute(command, COMMAND_TIMEOUT_MS);
                Instant commandEndedAt = Instant.now();
                results.add(new ToolCommandResult(command, result.exitCode(), result.stdout(), result.stderr(), commandStartedAt, commandEndedAt));
                runRecorder.recordCommand(run, sequence, command, result.exitCode(), result.stdout(), result.stderr(), commandStartedAt, commandEndedAt);
                if (result.exitCode() != 0) {
                    status = "FAILED";
                    break;
                }
            } catch (IOException ex) {
                Instant commandEndedAt = Instant.now();
                String error = safeError(ex);
                results.add(new ToolCommandResult(command, -1, "", error, commandStartedAt, commandEndedAt));
                runRecorder.recordCommand(run, sequence, command, -1, "", error, commandStartedAt, commandEndedAt);
                status = "FAILED";
                break;
            }
        }
        Instant endedAt = Instant.now();
        runRecorder.finish(run, status, endedAt);
        return new ToolRunResult(traceId, runtimeId, toolId, status, List.copyOf(results), startedAt, endedAt);
    }

    private ToolDefinition requireTool(String toolId) {
        ToolDefinition tool = tools.get(toolId);
        if (tool == null) throw new BusinessException(404, "OPERATION_TOOL_NOT_FOUND");
        return tool;
    }

    private static ToolDefinition readOnly(String id, Function<Map<String, String>, List<String>> renderer) {
        return new ToolDefinition(id, true, renderer, id.toUpperCase().replace('-', '_'));
    }

    private static List<String> kubernetesResourceCommands(Map<String, String> values) {
        String namespace = safeNamespace(values, "namespace", "default");
        String resource = choice(values, "resource", "pod", List.of("pod", "deployment", "statefulset", "daemonset", "service", "ingress", "job", "cronjob"));
        String name = optionalSafeName(values, "name");
        String target = name.isBlank() ? resource : resource + " " + name;
        return List.of(
                "kubectl get " + target + " -n " + namespace + " -o wide",
                "kubectl describe " + target + " -n " + namespace
        );
    }

    private static Map<String, String> safeMap(Map<String, String> values) {
        return values == null ? Map.of() : values;
    }

    private static String safeName(Map<String, String> values, String key) {
        String value = values.getOrDefault(key, "").trim();
        if (!SAFE_NAME.matcher(value).matches()) invalid(key);
        return value;
    }

    private static String safeHost(Map<String, String> values, String key) {
        String value = values.getOrDefault(key, "").trim();
        if (!Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,252}").matcher(value).matches())
            throw new BusinessException(400, "INVALID_TOOL_PARAMETER: " + key);
        return value;
    }

    private static String optionalSafeName(Map<String, String> values, String key) {
        String value = values.getOrDefault(key, "").trim();
        if (!value.isBlank() && !SAFE_NAME.matcher(value).matches()) invalid(key);
        return value;
    }

    private static String safeNamespace(Map<String, String> values, String key, String defaultValue) {
        String value = values.getOrDefault(key, defaultValue).trim();
        if (!SAFE_NAMESPACE.matcher(value).matches()) invalid(key);
        return value;
    }

    private static String positiveInteger(Map<String, String> values, String key, String defaultValue) {
        String value = values.getOrDefault(key, defaultValue).trim();
        if (!POSITIVE_INTEGER.matcher(value).matches()) invalid(key);
        return value;
    }

    private static String safeSearch(Map<String, String> values, String key) {
        String value = values.getOrDefault(key, "").trim();
        if (!SAFE_SEARCH.matcher(value).matches() || value.contains("'")) invalid(key);
        return value;
    }

    private static String choice(Map<String, String> values, String key, String defaultValue, List<String> allowed) {
        String value = values.getOrDefault(key, defaultValue).trim().toLowerCase();
        if (!allowed.contains(value)) invalid(key);
        return value;
    }

    private static void invalid(String key) {
        throw new BusinessException(400, "INVALID_TOOL_PARAMETER: " + key);
    }

    private static String safeError(IOException ex) {
        String message = ex.getMessage();
        return message == null || message.isBlank() ? "COMMAND_EXECUTION_FAILED" : message;
    }

    private record ToolDefinition(String id, boolean readOnly, Function<Map<String, String>, List<String>> renderer, String capability) {}

    private static final class NoOpRunRecorder implements OperationRunRecorder {
        public RunHandle start(String traceId, Long userId, OperationRuntime runtime, String toolId, Instant startedAt) {
            return new RunHandle(0L, traceId);
        }
        public void recordCommand(RunHandle run, int sequence, String command, int exitCode, String stdout,
                                  String stderr, Instant startedAt, Instant endedAt) {}
        public void finish(RunHandle run, String status, Instant endedAt) {}
    }
    public record ToolPreview(String toolId, boolean readOnly, List<String> commands) {}
    public record ToolDescriptor(String toolId, boolean readOnly, String riskLevel, boolean requireConfirm, String capability) {}
    public record ToolCommandResult(String command, int exitCode, String stdout, String stderr,
                                    Instant startedAt, Instant endedAt) {}
    public record ToolRunResult(String traceId, String runtimeId, String toolId, String status,
                                List<ToolCommandResult> commands, Instant startedAt, Instant endedAt) {}
}
