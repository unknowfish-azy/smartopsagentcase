package com.smartops.sentinel;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 哨兵监控 / 脚本库 / 告警中心 的 HTTP 接口。
 *
 * <p>契约与前端 {@code frontend/src/views/sentinel/sentinelStore.js} 中的
 * {@code SENTINEL_API} 一一对应。</p>
 *
 * <p><b>没有"直接执行脚本"的端点</b>：{@code POST /alerts/{id}/dispatch} 只登记
 * 待审批的处置意图并返回下一步说明，真正的执行必须走既有多机执行链路
 * （预览 → 审批 → 二次确认 → 执行）。这是刻意的设计，不是遗漏。</p>
 */
@RestController
@RequestMapping("/api/sentinel")
public class SentinelController {

    private final SentinelService sentinel;
    private final SentinelScriptRunner runner;
    private final AlertLifecycleService lifecycle;

    public SentinelController(SentinelService sentinel, SentinelScriptRunner runner,
                              AlertLifecycleService lifecycle) {
        this.sentinel = sentinel;
        this.runner = runner;
        this.lifecycle = lifecycle;
    }

    /* ── 哨兵任务 ─────────────────────────────────────────────────────── */

    @GetMapping("/tasks")
    public ApiResponse<List<SentinelService.TaskView>> tasks(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(sentinel.listTasks(actor));
    }

    /** 调度器最近一轮的实测指标与生效配置（队列年龄、到期延迟、背压、慢车道）。 */
    @GetMapping("/scheduler-stats")
    public ApiResponse<Map<String, Object>> schedulerStats(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(sentinel.schedulerStatus(actor));
    }

    @PostMapping("/tasks")
    public ApiResponse<SentinelService.TaskView> createTask(@AuthenticationPrincipal SessionUser actor,
                                                            @RequestBody TaskRequest request) {
        return ApiResponse.success(sentinel.createTask(actor, request.name(), request.kind(), request.target(),
                request.matchRule(), request.intervalSec() == null ? 60 : request.intervalSec(),
                request.templateId(), request.runtimeId(), request.groupLabel()));
    }

    @PatchMapping("/tasks/{id}/enabled")
    public ApiResponse<Void> toggleTask(@AuthenticationPrincipal SessionUser actor, @PathVariable long id,
                                        @RequestBody EnabledRequest request) {
        sentinel.setTaskEnabled(actor, id, request.enabled());
        return ApiResponse.success();
    }

    /**
     * 重绑运行连接。
     *
     * <p>后端重启或终端关闭后 runtimeId 失效，任务会显示「缺少运行连接」；
     * 重新连接会生成新的 runtimeId，这个端点把它写回任务，避免删任务重建。</p>
     */
    @PostMapping("/tasks/{id}/runtime")
    public ApiResponse<SentinelService.TaskView> rebindRuntime(@AuthenticationPrincipal SessionUser actor,
                                                              @PathVariable long id,
                                                              @RequestBody RebindRequest request) {
        return ApiResponse.success(sentinel.rebindRuntime(actor, id, request.sessionId()));
    }

    /** 资产分组列表（含任务数与启用数），供批量启停使用。 */
    @GetMapping("/task-groups")
    public ApiResponse<List<Map<String, Object>>> taskGroups(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(sentinel.listGroups(actor));
    }

    /** 按资产分组批量启停；返回实际改动的任务数。 */
    @PatchMapping("/task-groups/{label}/enabled")
    public ApiResponse<Map<String, Object>> toggleGroup(@AuthenticationPrincipal SessionUser actor,
                                                        @PathVariable String label,
                                                        @RequestBody EnabledRequest request) {
        int changed = sentinel.setGroupEnabled(actor, label, request.enabled());
        return ApiResponse.success(Map.of("label", label, "changed", changed, "enabled", request.enabled()));
    }

    /** 把某个哨兵任务改到另一个分组（空值表示取消分组）。 */
    @PatchMapping("/tasks/{id}/group")
    public ApiResponse<Void> assignGroup(@AuthenticationPrincipal SessionUser actor, @PathVariable long id,
                                         @RequestBody GroupRequest request) {
        sentinel.assignGroup(actor, id, request.groupLabel());
        return ApiResponse.success();
    }

    @DeleteMapping("/tasks/{id}")
    public ApiResponse<Void> deleteTask(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        sentinel.deleteTask(actor, id);
        return ApiResponse.success();
    }

    @GetMapping("/tasks/{id}/samples")
    public ApiResponse<List<SentinelService.SampleView>> samples(@AuthenticationPrincipal SessionUser actor,
                                                                 @PathVariable long id,
                                                                 @RequestParam(defaultValue = "300") int limit) {
        return ApiResponse.success(sentinel.listSamples(actor, id, limit));
    }

    /* ── 阈值模板 ─────────────────────────────────────────────────────── */

    @GetMapping("/threshold-templates")
    public ApiResponse<List<SentinelService.TemplateView>> templates(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(sentinel.listTemplates(actor));
    }

    @PostMapping("/threshold-templates")
    public ApiResponse<SentinelService.TemplateView> createTemplate(@AuthenticationPrincipal SessionUser actor,
                                                                    @RequestBody TemplateRequest request) {
        return ApiResponse.success(sentinel.createTemplate(actor, request.name(), request.description(),
                request.rules(), request.severity(), request.debounceSec() == null ? 300 : request.debounceSec()));
    }

    @DeleteMapping("/threshold-templates/{id}")
    public ApiResponse<Void> deleteTemplate(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        sentinel.deleteTemplate(actor, id);
        return ApiResponse.success();
    }

    /* ── 脚本库 ───────────────────────────────────────────────────────── */

    @GetMapping("/scripts")
    public ApiResponse<List<SentinelService.ScriptView>> scripts(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(sentinel.listScripts(actor));
    }

    @PostMapping("/scripts")
    public ApiResponse<SentinelService.ScriptView> createScript(@AuthenticationPrincipal SessionUser actor,
                                                                @RequestBody ScriptRequest request) {
        return ApiResponse.success(sentinel.createScript(actor, request.name(), request.language(),
                request.description(), request.tags(), request.riskLevel(), request.body(),
                request.timeoutSec() == null ? 60 : request.timeoutSec()));
    }

    /**
     * 从文件内容导入脚本。
     *
     * <p>上传与手动编写走**同一条**预检与存储路径（复用 {@code createScript}），
     * 因此不存在"上传能绕过高危预检"的缝隙。只接受文本，二进制与超大文件被拒。</p>
     */
    @PostMapping("/scripts/upload")
    public ApiResponse<SentinelService.ScriptView> uploadScript(@AuthenticationPrincipal SessionUser actor,
                                                                @RequestBody UploadScriptRequest request) {
        return ApiResponse.success(sentinel.uploadScript(actor, request.fileName(), request.content(),
                request.language(), request.riskLevel(), request.tags()));
    }

    @GetMapping("/scripts/{id}/versions")
    public ApiResponse<List<SentinelService.ScriptVersionView>> scriptVersions(@AuthenticationPrincipal SessionUser actor,
                                                                               @PathVariable long id) {
        return ApiResponse.success(sentinel.listScriptVersions(actor, id));
    }

    @DeleteMapping("/scripts/{id}")
    public ApiResponse<Void> deleteScript(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        sentinel.deleteScript(actor, id);
        return ApiResponse.success();
    }

    @PostMapping("/scripts/{id}/versions")
    public ApiResponse<SentinelService.ScriptView> addVersion(@AuthenticationPrincipal SessionUser actor,
                                                              @PathVariable long id,
                                                              @RequestBody VersionRequest request) {
        return ApiResponse.success(sentinel.addScriptVersion(actor, id, request.body()));
    }

    @GetMapping("/scripts/{id}/runs")
    public ApiResponse<List<SentinelService.RunView>> scriptRuns(@AuthenticationPrincipal SessionUser actor,
                                                                 @PathVariable long id) {
        return ApiResponse.success(sentinel.listRuns(actor, id));
    }

    @GetMapping("/runs")
    public ApiResponse<List<SentinelService.RunView>> runs(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(sentinel.listRuns(actor, null));
    }

    /**
     * 脚本高危预检。
     *
     * <p>这是给编辑器做即时反馈用的**只读**接口；真正的把关在保存与执行路径上，
     * 前端预检通过不等于服务端会放行。</p>
     */
    @PostMapping("/scripts/lint")
    public ApiResponse<SentinelScriptLint.Verdict> lint(@RequestBody LintRequest request) {
        return ApiResponse.success(SentinelScriptLint.lint(request.body(), request.language()));
    }

    /* ── 告警规则与告警 ───────────────────────────────────────────────── */

    @GetMapping("/alert-rules")
    public ApiResponse<List<SentinelService.AlertRuleView>> alertRules(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(sentinel.listAlertRules(actor));
    }

    @PostMapping("/alert-rules")
    public ApiResponse<SentinelService.AlertRuleView> createAlertRule(@AuthenticationPrincipal SessionUser actor,
                                                                      @RequestBody AlertRuleRequest request) {
        return ApiResponse.success(sentinel.createAlertRule(actor, request.name(), request.templateId(),
                request.severity(), request.scriptId(), Boolean.TRUE.equals(request.autoDispatch()),
                request.notifyChannels(), request.webhookUrl(), request.emailTo()));
    }

    @DeleteMapping("/alert-rules/{id}")
    public ApiResponse<Void> deleteAlertRule(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        sentinel.deleteAlertRule(actor, id);
        return ApiResponse.success();
    }

    @GetMapping("/alerts")
    public ApiResponse<List<SentinelService.AlertView>> alerts(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(sentinel.listAlerts(actor));
    }

    @PostMapping("/alerts/{id}/acknowledge")
    public ApiResponse<Void> acknowledge(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        sentinel.acknowledge(actor, id);
        return ApiResponse.success();
    }

    /** 发起处置：只进入待审批，不执行脚本。响应会说明下一步该走哪条链。 */
    @PostMapping("/alerts/{id}/dispatch")
    public ApiResponse<Map<String, Object>> dispatch(@AuthenticationPrincipal SessionUser actor, @PathVariable long id,
                                                     @RequestBody(required = false) DispatchRequest request) {
        return ApiResponse.success(sentinel.requestDispatch(actor, id, request == null ? null : request.scriptId()));
    }

    /** 回填执行结果（由既有多机执行链路的调用方回填）。 */
    @PostMapping("/alerts/{id}/result")
    public ApiResponse<Void> fillResult(@AuthenticationPrincipal SessionUser actor, @PathVariable long id,
                                        @RequestBody ResultRequest request) {
        sentinel.fillResult(actor, id, request.result(), request.exitCode(), request.excerpt());
        return ApiResponse.success();
    }

    @PostMapping("/alerts/{id}/close")
    public ApiResponse<Void> close(@AuthenticationPrincipal SessionUser actor, @PathVariable long id,
                                   @RequestBody(required = false) CloseRequest request) {
        sentinel.closeAlert(actor, id, request == null ? null : request.note());
        return ApiResponse.success();
    }

    /* ── 告警生命周期：分组 / 恢复 / 静默 / 转派升级 / 死信 ────────────── */

    /** 按分组看告警：同一故障的多次告警归成一组，优先显示还有几条没关。 */
    @GetMapping("/alerts/groups")
    public ApiResponse<List<AlertLifecycleService.GroupView>> alertGroups(
            @AuthenticationPrincipal SessionUser actor,
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(lifecycle.groups(actor, limit));
    }

    /** 手动触发一次恢复判定，返回本次自动进入待关闭的告警数。 */
    @PostMapping("/alerts/reconcile")
    public ApiResponse<Integer> reconcileAlerts(@RequestParam(defaultValue = "100") int limit) {
        return ApiResponse.success(lifecycle.resolveRecoveredAlerts(limit));
    }

    @GetMapping("/silences")
    public ApiResponse<List<AlertLifecycleService.SilenceView>> silences(
            @AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(lifecycle.listSilences(actor));
    }

    @PostMapping("/silences")
    public ApiResponse<AlertLifecycleService.SilenceView> createSilence(
            @AuthenticationPrincipal SessionUser actor,
            @RequestBody AlertLifecycleService.SilenceRequest request) {
        return ApiResponse.success(lifecycle.createSilence(actor, request));
    }

    @DeleteMapping("/silences/{id}")
    public ApiResponse<Void> cancelSilence(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        lifecycle.cancelSilence(actor, id);
        return ApiResponse.success();
    }

    /** 审批待生效的全局静默：仅管理员可操作，通过后才真正抑制告警。 */
    @PostMapping("/silences/{id}/approve")
    public ApiResponse<AlertLifecycleService.SilenceView> approveSilence(
            @AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        return ApiResponse.success(lifecycle.approveSilence(actor, id));
    }

    /** 转派告警负责人（不等于处置，处置仍走派单审批链）。 */
    @PostMapping("/alerts/{id}/transfer")
    public ApiResponse<Void> transfer(@AuthenticationPrincipal SessionUser actor, @PathVariable long id,
                                      @RequestBody TransferRequest request) {
        lifecycle.transfer(actor, id, request.assigneeId(), request.note());
        return ApiResponse.success();
    }

    /** 升级告警级别，只能往上调。 */
    @PostMapping("/alerts/{id}/escalate")
    public ApiResponse<String> escalate(@AuthenticationPrincipal SessionUser actor, @PathVariable long id,
                                        @RequestBody EscalateRequest request) {
        return ApiResponse.success(lifecycle.escalate(actor, id, request.severity(), request.note()));
    }

    /** 对失败的投递按原渠道重发一次。 */
    @PostMapping("/alerts/{id}/notifications/retry")
    public ApiResponse<Map<String, String>> retryNotification(@AuthenticationPrincipal SessionUser actor,
                                                              @PathVariable long id) {
        return ApiResponse.success(lifecycle.retryNotification(actor, id));
    }

    public record TransferRequest(long assigneeId, String note) {}

    public record EscalateRequest(String severity, String note) {}

    /**
     * AI 研判：产出**建议**（结论 + 证据 + 候选脚本），并落库供审阅。
     * 不改变告警状态、不触发执行。
     */
    @PostMapping("/alerts/{id}/analyze")
    public ApiResponse<SentinelAdvisor.Advice> analyze(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        return ApiResponse.success(sentinel.analyzeAlert(actor, id));
    }

    /**
     * 发送通知并返回**逐渠道真实结果**。
     *
     * <p>站内真实写入、Webhook 真实 HTTP、邮件在未配置 SMTP 时如实返回
     * `not_configured` —— 不把"没发出去"说成"已发送"。</p>
     */
    @PostMapping("/alerts/{id}/notify")
    public ApiResponse<Map<String, String>> notify(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        return ApiResponse.success(sentinel.notifyStakeholders(id, actor == null ? 0L : actor.id()));
    }

    /** 把已关闭的告警沉淀为知识候选，进入团队复核流程。 */
    @PostMapping("/alerts/{id}/knowledge")
    public ApiResponse<Map<String, Object>> knowledge(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        return ApiResponse.success(sentinel.createKnowledgeCandidate(actor, id));
    }

    @GetMapping("/knowledge-candidates")
    public ApiResponse<List<Map<String, Object>>> knowledgeCandidates(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(sentinel.listKnowledgeCandidates(actor));
    }

    /** 如实说明采集边界：会话级连接 → 常驻采集需要独立采集器。 */
    @GetMapping("/runtime-boundary")
    public ApiResponse<Map<String, String>> runtimeBoundary() {
        return ApiResponse.success(Map.of("note", SentinelService.runtimeBoundaryNote()));
    }

    /* ── 脚本执行（手动 / 定时 / 告警联动） ──────────────────────────── */

    /**
     * 发起一次脚本执行。
     *
     * <p><b>这里不会执行任何命令</b>：只生成既有 MultiExec 预览并把意图登记为待审批。
     * 真正执行必须由人通过 {@code POST /api/operations/multi-exec/execute} 提交
     * 预览 id 与确认码。响应中的 `previewId` / `confirmationNonce` 就是交给那一步的。</p>
     */
    @PostMapping("/scripts/{id}/prepare-run")
    public ApiResponse<Map<String, Object>> prepareRun(@AuthenticationPrincipal SessionUser actor,
                                                       @PathVariable long id,
                                                       @RequestBody PrepareRunRequest request) {
        return ApiResponse.success(runner.prepare(actor, id, request.trigger(), request.runtimeIds(),
                request.alertId(), request.variables()));
    }

    /** 回填真实执行结果（由既有执行链的调用方在拿到结果后回填）。 */
    @PostMapping("/runs/{runId}/result")
    public ApiResponse<Void> recordRunResult(@AuthenticationPrincipal SessionUser actor, @PathVariable long runId,
                                             @RequestBody RunResultRequest request) {
        runner.recordResult(actor, runId, request.result(), request.exitCode(), request.durationMs(), request.output());
        return ApiResponse.success();
    }

    /**
     * 执行记录详情：用于**回放**一次执行（谁、在哪、多久、返回码、完整输出、用了哪些变量）。
     *
     * <p>不含任何凭据：`run_id` 只是 MultiExec 的预览标识，确认码从不入库。</p>
     */
    @GetMapping("/runs/{runId}")
    public ApiResponse<Map<String, Object>> runDetail(@AuthenticationPrincipal SessionUser actor, @PathVariable long runId) {
        return ApiResponse.success(runner.runDetail(actor, runId));
    }

    /** 平台变量说明，供界面渲染变量面板（避免前端硬编码一份清单）。 */
    @GetMapping("/variables")
    public ApiResponse<Map<String, Object>> variables() {
        return ApiResponse.success(Map.of("supported", SentinelVariables.SUPPORTED,
                "note", "变量由服务端精确替换；含命令控制字符的变量值会被拒绝，不做 shell 展开。"));
    }

    /* ── 协作优化 4：团队 Agent 提出处置 ─────────────────────────────── */

    /**
     * 由团队 Agent 提出哨兵处置（等价于调用 `propose-remediation` 工具）。
     *
     * <p><b>不会执行命令</b>：它生成 MultiExec 预览并在团队侧创建一条
     * `PENDING_APPROVAL` 运行，后续仍要 preview → approve → consumeGrant。</p>
     */
    @PostMapping("/alerts/{id}/propose-remediation")
    public ApiResponse<Map<String, Object>> proposeRemediation(@AuthenticationPrincipal SessionUser actor,
                                                               @PathVariable long id,
                                                               @RequestBody ProposeRemediationRequest request) {
        return ApiResponse.success(runner.proposeRemediation(actor, request.teamId(), request.agentId(),
                request.versionId(), id, request.scriptId(), request.runtimeId()));
    }

    /* ── 定时计划 ─────────────────────────────────────────────────────── */

    @GetMapping("/schedules")
    public ApiResponse<List<SentinelScriptRunner.ScheduleView>> schedules(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(runner.listSchedules(actor));
    }

    /**
     * 创建定时计划。到点后只生成待审批预览，不执行命令。
     * 默认调度器未开启（见 SentinelPoller），需要部署方显式打开。
     */
    @PostMapping("/schedules")
    public ApiResponse<SentinelScriptRunner.ScheduleView> createSchedule(@AuthenticationPrincipal SessionUser actor,
                                                                         @RequestBody ScheduleRequest request) {
        java.time.Instant next = request.nextFireAt() == null ? null : java.time.Instant.parse(request.nextFireAt());
        return ApiResponse.success(runner.createSchedule(actor, request.scriptId(), request.cronExpr(),
                request.runtimeId(), next));
    }

    @DeleteMapping("/schedules/{id}")
    public ApiResponse<Void> deleteSchedule(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        runner.deleteSchedule(actor, id);
        return ApiResponse.success();
    }

    /* ── 请求体 ───────────────────────────────────────────────────────── */

    public record ScheduleRequest(long scriptId, String cronExpr, String runtimeId, String nextFireAt) {}

    public record ProposeRemediationRequest(long teamId, long agentId, long versionId, long scriptId,
                                            String runtimeId) {}

    public record PrepareRunRequest(String trigger, List<String> runtimeIds, Long alertId,
                                    Map<String, String> variables) {}

    public record RunResultRequest(String result, Integer exitCode, Long durationMs, String output) {}

    public record TaskRequest(String name, String kind, String target, String matchRule, Integer intervalSec,
                              Long templateId, String runtimeId, String groupLabel) {}

    public record EnabledRequest(boolean enabled) {}

    public record RebindRequest(Long sessionId) {}

    public record GroupRequest(String groupLabel) {}

    public record TemplateRequest(String name, String description, Object rules, String severity, Integer debounceSec) {}

    public record ScriptRequest(String name, String language, String description, String tags, String riskLevel,
                                String body, Integer timeoutSec) {}

    public record VersionRequest(String body) {}

    public record UploadScriptRequest(String fileName, String content, String language, String riskLevel, String tags) {}

    public record LintRequest(String body, String language) {}

    public record AlertRuleRequest(String name, Long templateId, String severity, Long scriptId, Boolean autoDispatch,
                                   String notifyChannels, String webhookUrl, String emailTo) {}

    public record DispatchRequest(Long scriptId) {}

    public record ResultRequest(String result, Integer exitCode, String excerpt) {}

    public record CloseRequest(String note) {}
}
