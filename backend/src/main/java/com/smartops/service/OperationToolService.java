package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.regex.Pattern;

/**
 * 云运维工具目录与执行入口。
 *
 * <p><b>OPS-01</b>：目录不再只回答"叫什么、要不要确认"，而是对每个工具声明
 * 实现状态（真实适配 / 仅模板 / 不可用）、输入输出 Schema、目标类型、风险、
 * 所需权限、凭据引用、总超时、输出预算、幂等语义与核验方式。
 * 这样前端、团队 Agent 和审计看到的是同一份事实，而不是"命令模板看起来像实现了"。</p>
 *
 * <p><b>OPS-04</b>：执行侧补齐绝对 deadline、取消、心跳、输出预算和幂等键；
 * 远端动作后超时归为 {@code UNCERTAIN}，不冒充失败也不冒充成功。</p>
 */
@Service
public class OperationToolService {

    private static final Logger log = LoggerFactory.getLogger(OperationToolService.class);

    private static final long COMMAND_TIMEOUT_MS = 30_000;
    private static final Pattern SAFE_NAME = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");
    private static final Pattern SAFE_NAMESPACE = Pattern.compile("[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?");
    private static final Pattern POSITIVE_INTEGER = Pattern.compile("[1-9][0-9]{0,5}");
    private static final Pattern SAFE_SEARCH = Pattern.compile("[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,127}");
    private static final Pattern SAFE_RELATIVE_PATH = Pattern.compile("[A-Za-z0-9._][A-Za-z0-9._/-]{0,255}");

    /** 目录声明的输出 Schema 基线：所有命令型工具都以这四项作为证据骨架。 */
    private static final List<String> COMMAND_OUTPUT_SCHEMA =
            List.of("exitCode:int", "stdout:text", "stderr:text", "truncated:bool", "startedAt:instant", "endedAt:instant");

    private static final Map<String, ToolParameter> PARAMS = params();

    private final OperationRuntimeRegistry registry;
    private final OperationRunRecorder runRecorder;
    private final Map<String, ToolDefinition> tools;
    private final ObservabilityService observability;
    private final long runDeadlineMs;
    private final int outputLimitBytes;
    private final long leaseMs;
    private final long recoveryStaleMs;

    public OperationToolService(OperationRuntimeRegistry registry) {
        this(registry, new NoOpRunRecorder());
    }

    public OperationToolService(OperationRuntimeRegistry registry, OperationRunRecorder runRecorder) {
        this(registry, runRecorder, null);
    }

    public OperationToolService(OperationRuntimeRegistry registry, OperationRunRecorder runRecorder, ObservabilityService observability) {
        this(registry, runRecorder, observability,
                JdbcOperationRunRecorder.DEFAULT_DEADLINE_MS, 512 * 1024, JdbcOperationRunRecorder.DEFAULT_LEASE_MS, 90_000);
    }

    @Autowired
    public OperationToolService(OperationRuntimeRegistry registry, OperationRunRecorder runRecorder, ObservabilityService observability,
                                @Value("${smartops.operations.run.deadline-ms:120000}") long runDeadlineMs,
                                @Value("${smartops.operations.run.output-limit-bytes:524288}") int outputLimitBytes,
                                @Value("${smartops.operations.run.lease-ms:60000}") long leaseMs,
                                @Value("${smartops.operations.run.recovery-stale-ms:90000}") long recoveryStaleMs) {
        this.registry = registry;
        this.runRecorder = runRecorder;
        this.observability = observability;
        this.runDeadlineMs = runDeadlineMs;
        this.outputLimitBytes = outputLimitBytes;
        this.leaseMs = leaseMs;
        this.recoveryStaleMs = recoveryStaleMs;
        this.tools = catalog();
    }

    /** 恢复扫描的悬挂阈值（超过该时长无心跳视为悬挂）。 */
    public long recoveryStaleMs() { return recoveryStaleMs; }

    /* ── 能力目录 ─────────────────────────────────────────────────────── */

    private Map<String, ToolDefinition> catalog() {
        Map<String, ToolDefinition> entries = new LinkedHashMap<>();
        add(entries, real("docker-compose-status", values -> List.of("docker compose ls --all --format json")));
        add(entries, real("helm-releases", values -> List.of(
                "helm list -n " + safeNamespace(values, "namespace", "default") + " --max 100 -o json")).params("namespace"));
        add(entries, real("k8s-storage", values -> List.of(
                "kubectl get pvc -n " + safeNamespace(values, "namespace", "default") + " -o wide",
                "kubectl get storageclass")).params("namespace"));
        add(entries, real("k8s-rbac-check", values -> List.of(
                "kubectl auth can-i get pods -n " + safeNamespace(values, "namespace", "default"),
                "kubectl auth can-i get pods --subresource=log -n " + safeNamespace(values, "namespace", "default"))).params("namespace"));
        add(entries, real("mesh-status", values -> List.of(
                "kubectl get pods,services -n " + safeNamespace(values, "namespace", "istio-system") + " -o wide")).params("namespace"));
        add(entries, real("terraform-environment", values -> List.of("terraform version -json")));
        // OPS-12：validate / plan / show 只读三件套；plan/show 的结构化输出交给 /api/iac/plans/analyze
        // 脱敏并识别 destroy/replace，审批与下发不在工具层直接完成。
        add(entries, real("terraform-validate", values -> List.of(
                "cd " + safeRelativePath(values, "directory") + " && terraform validate -json -no-color"))
                .params("directory")
                .verification("validate 只证明语法与引用合法，不代表计划可安全应用；需继续审阅 plan 的 destroy/replace"));
        add(entries, real("terraform-plan", values -> List.of(
                "cd " + safeRelativePath(values, "directory") + " && terraform plan -input=false -no-color"))
                .params("directory")
                .verification("plan 输出必须经 /api/iac/plans 保存并审批，禁止直接 apply"));
        add(entries, real("terraform-show", values -> List.of(
                "cd " + safeRelativePath(values, "directory") + " && terraform show -json "
                        + safeRelativePath(values, "planFile")))
                .params("directory", "planFile")
                .verification("show -json 需经 /api/iac/plans/analyze 脱敏并识别销毁，不可直接应用"));
        add(entries, real("harbor-endpoint-check", values -> List.of(
                "curl --fail --silent --show-error --max-time 10 https://" + safeHost(values, "host") + "/api/v2.0/health")).params("host"));
        add(entries, real("containerd-registry-inspect", values -> List.of(
                "ctr namespaces list", "ctr -n " + safeNamespace(values, "namespace", "k8s.io") + " images list",
                "ctr plugins ls")).params("namespace"));
        add(entries, real("containerd-config-check", values -> List.of(
                "containerd config dump", "find /etc/containerd/certs.d -maxdepth 3 -name hosts.toml -print")));
        add(entries, real("host-health", values -> List.of(
                "uptime", "free -h", "df -hT", "ss -lntup")));
        add(entries, real("system-logs", values -> List.of(
                "journalctl -p " + choice(values, "priority", "warning", List.of("emerg", "alert", "crit", "err", "warning", "notice", "info"))
                        + " -n " + positiveInteger(values, "lines", "200") + " --no-pager")).params("priority", "lines"));
        add(entries, real("docker-containers", values -> List.of(
                "docker ps --no-trunc", "docker stats --no-stream")));
        add(entries, real("docker-logs", values -> List.of(
                "docker logs --tail " + positiveInteger(values, "tail", "200") + " " + safeName(values, "container"))).params("container", "tail"));
        add(entries, real("k8s-resources", OperationToolService::kubernetesResourceCommands).params("namespace", "resource", "name"));
        add(entries, real("k8s-logs", values -> {
            String namespace = safeNamespace(values, "namespace", "default");
            String pod = safeName(values, "pod");
            String container = optionalSafeName(values, "container");
            String suffix = container.isBlank() ? "" : " -c " + container;
            return List.of("kubectl logs " + pod + suffix + " -n " + namespace + " --tail="
                    + positiveInteger(values, "tail", "200"));
        }).params("namespace", "pod", "container", "tail"));
        add(entries, real("log-search", values -> List.of(
                "journalctl -u " + safeName(values, "service") + " -n " + positiveInteger(values, "lines", "200")
                        + " --no-pager | grep -i -- '" + safeSearch(values, "keyword") + "'")).params("service", "keyword", "lines"));
        add(entries, real("network-diagnostics", values -> List.of(
                "ping -c 3 " + safeName(values, "host"),
                "nc -vz -w 5 " + safeName(values, "host") + " " + positiveInteger(values, "port", "443"),
                "dig " + safeName(values, "host"))).params("host", "port"));
        add(entries, real("alerts-query", values -> List.of(
                "curl --fail --silent http://alertmanager:9093/api/v2/alerts")).target("ALERTMANAGER"));
        add(entries, real("prometheus-query", values -> List.of(
                "HTTP GET configured Prometheus /api/v1/query_range (read-only)")).target("PROMETHEUS")
                .credential("smartops.observability.prometheus-url").params("query", "range"));
        add(entries, real("loki-log-query", values -> List.of(
                "HTTP GET configured Loki /loki/api/v1/query_range (read-only)")).target("LOKI")
                .credential("smartops.observability.loki-url").params("selector", "lines"));
        add(entries, real("k8s-diagnose", values -> {
            String namespace = safeNamespace(values, "namespace", "default");
            String name = safeName(values, "name");
            return List.of(
                    "kubectl get pod,deploy,svc,endpoints -n " + namespace + " -l app=" + name + " -o wide",
                    "kubectl get events -n " + namespace + " --sort-by=.lastTimestamp");
        }).params("namespace", "name"));
        // ── 以下两项只有命令模板，仓库内没有配套 smartops CLI 实现 ──
        add(entries, template("knowledge-retrieval", "知识检索需要 smartops CLI 或知识服务适配器，本仓库未实现",
                values -> List.of("smartops knowledge search --query '" + safeSearch(values, "keyword") + "' --top-k " + positiveInteger(values, "topK", "5")),
                "keyword", "topK"));
        add(entries, template("grafana-dashboard", "Grafana 面板读取需要 Grafana API 适配器与凭据，本仓库未实现",
                values -> List.of("smartops grafana panel --dashboard " + safeName(values, "dashboard")
                        + " --panel " + safeName(values, "panel") + " --read-only"),
                "dashboard", "panel"));
        // 数据库诊断已由进程内 JDBC 适配器实现：这里不再渲染仓库中不存在的 smartops CLI。
        add(entries, real("database-readonly", values -> List.of(
                "# 数据库只读诊断由进程内 JDBC 适配器执行：POST /api/operations/database/diagnose"
                        + "（engine/host/port/database/credentialRef），只读会话 + 单语句 + 行数/字节/耗时上限"))
                .target("DATABASE").credential("database-readonly").params("metric"));
        add(entries, real("mysql-slow-query", values -> List.of(
                "# 慢 SQL 诊断 metric=SLOW_SQL 走同一端点：POST /api/operations/database/diagnose，"
                        + "DIGEST_TEXT 脱敏后进入证据"))
                .target("DATABASE").credential("database-readonly").params("database", "limit"));
        // ── 告警静默：走真实静默 API（审批 + TTL + 撤销），不再以不可用占位 ──
        add(entries, mutating("alerts-suppress", "ALERT_SUPPRESS", values -> List.of(
                "# 静默走 POST /api/alerts/silences：GLOBAL 超过 24 小时需管理员审批，窗口上限 7 天，"
                        + "外部平台同步失败如实标记 externalStatus；撤销走 DELETE /api/alerts/silences/{id}；目标告警 "
                        + safeName(values, "alert")))
                .params("alert")
                .verification("静默只阻止新告警与通知，不修改已有告警状态；生效前确认告警对象、范围与窗口"));
        // 告警联动处置的受控入口：本身不渲染可执行命令，只声明"有资格提出处置"。
        add(entries, mutating("propose-remediation", "SENTINEL_REMEDIATION", values -> List.of(
                "# 提交哨兵处置建议：告警 " + safeName(values, "alertId")
                        + " / 脚本 " + safeName(values, "scriptId")
                        + " —— 需生成预览并人工审批后执行")).params("alertId", "scriptId"));
        add(entries, mutating("service-restart", "SERVICE_RESTART", values ->
                List.of("systemctl restart " + safeName(values, "service"))).params("service")
                .verification("重启后需独立验证：服务进程、监听端口、业务探针与错误率，不以退出码 0 代替恢复"));
        return Map.copyOf(entries);
    }

    private static void register(Map<String, ToolDefinition> entries, ToolDefinition definition) {
        ToolDefinition existing = entries.putIfAbsent(definition.id(), definition);
        if (existing != null) {
            // 同名工具必须显式处理，不能靠 Map 覆盖让其中一个静默消失。
            throw new IllegalStateException("TOOL_CATALOG_DUPLICATE_ID: " + definition.id());
        }
    }

    public ToolPreview preview(Long userId, String toolId, Map<String, String> parameters) {
        ToolDefinition tool = requireTool(toolId);
        return new ToolPreview(tool.id(), tool.readOnly(),
                List.copyOf(tool.renderer().apply(safeMap(parameters))));
    }

    public List<ToolDescriptor> listTools() {
        return tools.values().stream()
                .map(tool -> new ToolDescriptor(
                        tool.id(), tool.version(), tool.implementationStatus().name(), tool.readOnly(), tool.risk(),
                        !tool.readOnly(), tool.capability(), tool.targetType(), tool.requiredScope(),
                        tool.credentialRef(), tool.deadlineMs(), tool.outputLimitBytes(), tool.idempotency(),
                        tool.verification(), tool.inputSchema(), tool.outputSchema(), tool.unavailableReason()))
                .sorted(Comparator.comparing(ToolDescriptor::toolId))
                .toList();
    }

    public ToolRunResult execute(Long userId, String runtimeId, String toolId, Map<String, String> parameters) {
        return executeInternal(userId, runtimeId, toolId, parameters, false, null);
    }

    public ToolRunResult executeApprovedTeamRun(Long userId, String runtimeId, String toolId, Map<String, String> parameters) {
        return executeApprovedTeamRun(userId, runtimeId, toolId, parameters, null);
    }

    /**
     * 审批后执行。
     *
     * @param idempotencyKey 同一审批单只允许执行一次；重复调用直接拒绝，避免重复副作用
     */
    public ToolRunResult executeApprovedTeamRun(Long userId, String runtimeId, String toolId, Map<String, String> parameters,
                                                String idempotencyKey) {
        // propose-remediation 是"提议"而非"执行"：必须经 SentinelScriptRunner 生成
        // MultiExec 预览后由人确认，不允许从这个通用执行入口直接跑掉。
        if ("propose-remediation".equals(toolId)) {
            throw new BusinessException(409, "TEAM_REMEDIATION_REQUIRES_SENTINEL_PREVIEW");
        }
        return executeInternal(userId, runtimeId, toolId, parameters, true, idempotencyKey);
    }

    private ToolRunResult executeInternal(Long userId, String runtimeId, String toolId, Map<String, String> parameters,
                                          boolean approvedTeamRun, String idempotencyKey) {
        ToolDefinition tool = requireTool(toolId);
        if (!tool.readOnly() && !approvedTeamRun) throw new BusinessException(409, "TOOL_CONFIRMATION_REQUIRED");
        if (tool.implementationStatus() == ImplementationStatus.UNAVAILABLE) {
            log.warn("tool unavailable toolId={} reason={}", toolId, tool.unavailableReason());
            throw new BusinessException(501, "TEAM_TOOL_NOT_IMPLEMENTED");
        }
        if (tool.implementationStatus() == ImplementationStatus.TEMPLATE) {
            // 有模板不等于有实现：宁可如实拒绝，也不要让退出码 127 冒充"执行失败"。
            log.warn("tool template-only toolId={} reason={}", toolId, tool.unavailableReason());
            throw new BusinessException(501, "TOOL_IMPLEMENTATION_UNAVAILABLE");
        }
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        if (!runtime.isOpen()) throw new BusinessException(409, "RUNTIME_CLOSED");

        if (toolId.equals("prometheus-query") || toolId.equals("loki-log-query")) {
            return executeHttpQuery(userId, runtimeId, toolId, parameters, tool);
        }

        ToolPreview preview = preview(userId, toolId, parameters);
        Instant startedAt = Instant.now();
        Instant deadlineAt = startedAt.plusMillis(tool.deadlineMs());
        String traceId = UUID.randomUUID().toString();
        String key = idempotencyKey == null || idempotencyKey.isBlank()
                ? null : "tool-run:" + userId + ":" + idempotencyKey.trim();
        OperationRunRecorder.RunHandle run = runRecorder.start(new OperationRunRecorder.RunSpec(
                traceId, userId, runtime, toolId, key, startedAt, deadlineAt, tool.outputLimitBytes(), leaseMs));
        List<ToolCommandResult> results = new ArrayList<>();
        String status = "SUCCEEDED";
        int sequence = 0;
        for (String command : preview.commands()) {
            if (runRecorder.cancelRequested(run)) {
                status = "CANCELLED";
                runRecorder.recordEvidence(run, "RUN_CANCELLED", "操作者在命令之间请求取消；后续命令未派发");
                break;
            }
            long remainingMs = deadlineAt.toEpochMilli() - Instant.now().toEpochMilli();
            if (remainingMs <= 0) {
                status = "TIMEOUT";
                runRecorder.recordEvidence(run, "RUN_DEADLINE_EXCEEDED", "整单预算耗尽；后续命令未派发，不视为远端动作已完成");
                break;
            }
            sequence++;
            Instant commandStartedAt = Instant.now();
            try {
                OperationRuntime.CommandResult result = runtime.execute(command, Math.min(COMMAND_TIMEOUT_MS, remainingMs));
                Instant commandEndedAt = Instant.now();
                Bounded bounded = bound(result.stdout(), result.stderr(), tool.outputLimitBytes());
                results.add(new ToolCommandResult(command, result.exitCode(), bounded.stdout(), bounded.stderr(),
                        commandStartedAt, commandEndedAt, bounded.truncated()));
                runRecorder.recordCommand(run, sequence, command, result.exitCode(), bounded.stdout(), bounded.stderr(),
                        commandStartedAt, commandEndedAt, bounded.truncated());
                if (result.exitCode() != 0) {
                    status = "FAILED";
                    break;
                }
            } catch (IOException ex) {
                Instant commandEndedAt = Instant.now();
                String error = safeError(ex);
                if (isTimeout(ex) && !tool.readOnly()) {
                    // 写操作在远端可能已经开始，超时后既不能报成功，也不能当成可安全重试的失败。
                    status = "UNCERTAIN";
                    results.add(new ToolCommandResult(command, -1, "", error, commandStartedAt, commandEndedAt, false));
                    runRecorder.recordCommand(run, sequence, command, -1, "", error, commandStartedAt, commandEndedAt, false);
                    runRecorder.recordEvidence(run, "COMMAND_TIMEOUT_UNCERTAIN",
                            "写操作命令超时，远端是否生效未知；需人工核验，禁止直接重试");
                    break;
                }
                results.add(new ToolCommandResult(command, -1, "", error, commandStartedAt, commandEndedAt, false));
                runRecorder.recordCommand(run, sequence, command, -1, "", error, commandStartedAt, commandEndedAt, false);
                status = "FAILED";
                break;
            }
            runRecorder.heartbeat(run);
        }
        Instant endedAt = Instant.now();
        runRecorder.finish(run, status, endedAt);
        return new ToolRunResult(traceId, runtimeId, toolId, status, List.copyOf(results), startedAt, endedAt);
    }

    private ToolRunResult executeHttpQuery(Long userId, String runtimeId, String toolId, Map<String, String> parameters,
                                           ToolDefinition tool) {
        if (observability == null) throw new BusinessException(503, "OBSERVABILITY_NOT_CONFIGURED");
        Map<String, String> values = safeMap(parameters);
        boolean prometheus = toolId.equals("prometheus-query");
        Instant started = Instant.now();
        var response = observability.query(userId, prometheus ? "prometheus" : "loki",
                values.getOrDefault(prometheus ? "query" : "selector", prometheus ? "up" : "{app=\"api\"}"),
                Integer.parseInt(positiveInteger(values, "range", "15")),
                Integer.parseInt(positiveInteger(values, "lines", "200")));
        Instant finished = Instant.now();
        Bounded bounded = bound(response.response().toString(), "", tool.outputLimitBytes());
        return new ToolRunResult(response.traceId(), runtimeId, toolId, "SUCCEEDED", List.of(
                new ToolCommandResult("HTTP " + response.source() + " read-only query", 0,
                        bounded.stdout(), "", started, finished, bounded.truncated())), started, finished);
    }

    private ToolDefinition requireTool(String toolId) {
        ToolDefinition tool = tools.get(toolId);
        if (tool == null) throw new BusinessException(404, "OPERATION_TOOL_NOT_FOUND");
        return tool;
    }

    /* ── 工具声明构造器 ───────────────────────────────────────────────── */

    private static Spec real(String id, Function<Map<String, String>, List<String>> renderer) {
        return new Spec(id, true, ImplementationStatus.REAL, capabilityOf(id), renderer);
    }

    private static Spec template(String id, String reason, Function<Map<String, String>, List<String>> renderer,
                                 String... parameterNames) {
        Spec spec = new Spec(id, true, ImplementationStatus.TEMPLATE, capabilityOf(id), renderer);
        spec.unavailableReason = reason;
        spec.verification = "当前不可执行：目录已标记为 TEMPLATE，需接入真实适配器并通过验收后再置为 REAL";
        return spec.params(parameterNames);
    }

    private static Spec unavailable(String id, String capability, String reason,
                                    Function<Map<String, String>, List<String>> renderer, String... parameterNames) {
        Spec spec = new Spec(id, false, ImplementationStatus.UNAVAILABLE, capability, renderer);
        spec.unavailableReason = reason;
        spec.verification = "当前不可执行：外部平台写入未接入；目录如实标记 UNAVAILABLE";
        return spec.params(parameterNames);
    }

    private static Spec mutating(String id, String capability, Function<Map<String, String>, List<String>> renderer) {
        return new Spec(id, false, ImplementationStatus.REAL, capability, renderer);
    }

    private static String capabilityOf(String id) {
        return id.toUpperCase().replace('-', '_');
    }

    private static Map<String, ToolParameter> params() {
        Map<String, ToolParameter> map = new LinkedHashMap<>();
        map.put("namespace", new ToolParameter("namespace", "ns:[a-z0-9.-]", false, "Kubernetes / Helm 命名空间"));
        map.put("host", new ToolParameter("host", "host", true, "授权目标主机或域名"));
        map.put("port", new ToolParameter("port", "int:1-65535", false, "目标端口，默认 443"));
        map.put("container", new ToolParameter("container", "name", false, "容器名称"));
        map.put("pod", new ToolParameter("pod", "name", true, "Pod 名称"));
        map.put("resource", new ToolParameter("resource", "pod|deployment|statefulset|daemonset|service|ingress|job|cronjob", false, "资源类型"));
        map.put("name", new ToolParameter("name", "name", true, "资源名称"));
        map.put("service", new ToolParameter("service", "name", true, "systemd 服务名"));
        map.put("keyword", new ToolParameter("keyword", "text", true, "检索关键词（禁止引号）"));
        map.put("lines", new ToolParameter("lines", "int", false, "日志行数，默认 200"));
        map.put("tail", new ToolParameter("tail", "int", false, "日志尾部行数，默认 200"));
        map.put("priority", new ToolParameter("priority", "emerg|alert|crit|err|warning|notice|info", false, "journalctl 级别"));
        map.put("topK", new ToolParameter("topK", "int", false, "返回条数，默认 5"));
        map.put("metric", new ToolParameter("metric", "name", true, "指标名"));
        map.put("query", new ToolParameter("query", "promql", false, "PromQL，默认 up"));
        map.put("range", new ToolParameter("range", "int:minutes", false, "时间范围（分钟），默认 15"));
        map.put("dashboard", new ToolParameter("dashboard", "name", true, "Grafana 看板标识"));
        map.put("panel", new ToolParameter("panel", "name", false, "Grafana 面板标识"));
        map.put("selector", new ToolParameter("selector", "logql", false, "Loki 标签选择器"));
        map.put("database", new ToolParameter("database", "name", true, "数据库名"));
        map.put("limit", new ToolParameter("limit", "int", false, "返回条数，默认 20"));
        map.put("alert", new ToolParameter("alert", "name", true, "告警名称"));
        map.put("alertId", new ToolParameter("alertId", "name", true, "告警 ID"));
        map.put("scriptId", new ToolParameter("scriptId", "name", true, "脚本 ID"));
        map.put("directory", new ToolParameter("directory", "relative-path", true, "Terraform 工作目录（相对路径，禁止 ..）"));
        map.put("planFile", new ToolParameter("planFile", "relative-path", true, "plan 文件相对路径"));
        return Map.copyOf(map);
    }

    /** 目录声明对象：可变 builder 只在构造期使用，对外仍以不可变 record 暴露。 */
    private static final class Spec {
        private final String id;
        private final boolean readOnly;
        private final ImplementationStatus status;
        private final String capability;
        private final Function<Map<String, String>, List<String>> renderer;
        private String targetType = "REMOTE_HOST";
        private String credentialRef = "runtime-session";
        private String verification = "命令退出码 + 结构化输出；只读工具需人工核对输出内容再下结论";
        private String unavailableReason;
        private List<ToolParameter> inputSchema = List.of();
        private List<String> outputSchema = COMMAND_OUTPUT_SCHEMA;

        private Spec(String id, boolean readOnly, ImplementationStatus status, String capability,
                     Function<Map<String, String>, List<String>> renderer) {
            this.id = id;
            this.readOnly = readOnly;
            this.status = status;
            this.capability = capability;
            this.renderer = renderer;
        }

        private Spec params(String... names) {
            List<ToolParameter> schema = new ArrayList<>();
            for (String name : names) {
                ToolParameter parameter = PARAMS.get(name);
                if (parameter == null) throw new IllegalStateException("TOOL_PARAMETER_UNDECLARED: " + id + "." + name);
                schema.add(parameter);
            }
            this.inputSchema = List.copyOf(schema);
            return this;
        }

        private Spec target(String value) { this.targetType = value; return this; }

        private Spec credential(String value) { this.credentialRef = value; return this; }

        private Spec verification(String value) { this.verification = value; return this; }

        private ToolDefinition build(long deadlineMs, int outputLimitBytes) {
            return new ToolDefinition(id, "1", status, readOnly, capability, targetType,
                    readOnly ? "LOW" : "HIGH", "TOOL:" + capability + (readOnly ? ":READ" : ":WRITE"),
                    credentialRef, readOnly ? "SAFE_RETRY" : "AT_MOST_ONCE", deadlineMs, outputLimitBytes,
                    verification, inputSchema, outputSchema,
                    status == ImplementationStatus.REAL ? null : unavailableReason, renderer);
        }
    }

    /** 在能力目录初始化时，把每个 Spec 落成声明对象（预算参数来自服务配置）。 */
    private void add(Map<String, ToolDefinition> entries, Spec spec) {
        register(entries, spec.build(runDeadlineMs, outputLimitBytes));
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

    /* ── 参数校验 ─────────────────────────────────────────────────────── */

    private static Map<String, String> safeMap(Map<String, String> values) {
        return values == null ? Map.of() : values;
    }

    private static String safeName(Map<String, String> values, String key) {
        String value = values.getOrDefault(key, "").trim();
        if (!SAFE_NAME.matcher(value).matches()) invalid(key);
        return value;
    }

    private static String safeRelativePath(Map<String, String> values, String key) {
        String value = values.getOrDefault(key, "").trim();
        if (!SAFE_RELATIVE_PATH.matcher(value).matches() || value.contains("..")) invalid(key);
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

    private static boolean isTimeout(IOException ex) {
        return "COMMAND_TIMEOUT".equals(ex.getMessage());
    }

    /** 输出预算：超出部分截断并保留标记，避免把 100 MB 输出塞进内存和数据库。 */
    private static Bounded bound(String stdout, String stderr, int limitBytes) {
        String out = stdout == null ? "" : stdout;
        String err = stderr == null ? "" : stderr;
        boolean truncated = false;
        if (byteLength(out) + byteLength(err) > limitBytes) {
            truncated = true;
            int stdoutBudget = Math.max(1, limitBytes / 2);
            out = truncateToBytes(out, stdoutBudget);
            err = truncateToBytes(err, (int) Math.max(1, limitBytes - byteLength(out)));
        }
        return new Bounded(out, err, truncated);
    }

    private static String truncateToBytes(String value, int limitBytes) {
        if (byteLength(value) <= limitBytes) return value;
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        String cut = new String(bytes, 0, Math.max(0, limitBytes), StandardCharsets.UTF_8);
        return cut + "\n[TRUNCATED: output exceeded " + limitBytes + " bytes]";
    }

    private static long byteLength(String value) {
        return value == null ? 0L : value.getBytes(StandardCharsets.UTF_8).length;
    }

    /* ── 声明与结果模型 ───────────────────────────────────────────────── */

    public enum ImplementationStatus { REAL, TEMPLATE, UNAVAILABLE }

    private record ToolDefinition(String id, String version, ImplementationStatus implementationStatus, boolean readOnly,
                                  String capability, String targetType, String risk, String requiredScope,
                                  String credentialRef, String idempotency, long deadlineMs, int outputLimitBytes,
                                  String verification, List<ToolParameter> inputSchema, List<String> outputSchema,
                                  String unavailableReason,
                                  Function<Map<String, String>, List<String>> renderer) {}

    public record ToolParameter(String name, String format, boolean required, String description) {}

    /**
     * 目录对外模型。
     *
     * <p>保留 5 参数构造器是为了兼容既有调用方（含测试），新字段全部有默认值。</p>
     */
    public record ToolDescriptor(String toolId, String version, String implementationStatus, boolean readOnly,
                                 String riskLevel, boolean requireConfirm, String capability, String targetType,
                                 String requiredScope, String credentialRef, long deadlineMs, int outputLimitBytes,
                                 String idempotency, String verification, List<ToolParameter> inputSchema,
                                 List<String> outputSchema, String unavailableReason) {
        public ToolDescriptor(String toolId, boolean readOnly, String riskLevel, boolean requireConfirm, String capability) {
            this(toolId, "1", "REAL", readOnly, riskLevel, requireConfirm, capability, "REMOTE_HOST",
                    "TOOL:" + capability + (readOnly ? ":READ" : ":WRITE"), "runtime-session",
                    JdbcOperationRunRecorder.DEFAULT_DEADLINE_MS, 512 * 1024,
                    readOnly ? "SAFE_RETRY" : "AT_MOST_ONCE", "", List.of(), COMMAND_OUTPUT_SCHEMA, null);
        }
    }

    private static final class NoOpRunRecorder implements OperationRunRecorder {
        public RunHandle start(String traceId, Long userId, OperationRuntime runtime, String toolId, Instant startedAt) {
            return new RunHandle(0L, traceId);
        }
        public void recordCommand(RunHandle run, int sequence, String command, int exitCode, String stdout,
                                  String stderr, Instant startedAt, Instant endedAt) {}
        public void finish(RunHandle run, String status, Instant endedAt) {}
    }

    public record ToolPreview(String toolId, boolean readOnly, List<String> commands) {}
    public record ToolCommandResult(String command, int exitCode, String stdout, String stderr,
                                    Instant startedAt, Instant endedAt, boolean truncated) {
        public ToolCommandResult(String command, int exitCode, String stdout, String stderr,
                                 Instant startedAt, Instant endedAt) {
            this(command, exitCode, stdout, stderr, startedAt, endedAt, false);
        }
    }
    public record ToolRunResult(String traceId, String runtimeId, String toolId, String status,
                                List<ToolCommandResult> commands, Instant startedAt, Instant endedAt) {}

    private record Bounded(String stdout, String stderr, boolean truncated) {}
}
