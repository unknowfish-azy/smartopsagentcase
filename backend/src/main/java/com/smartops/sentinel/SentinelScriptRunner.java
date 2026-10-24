package com.smartops.sentinel;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.service.MultiExecService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 脚本执行编排：手动 / 定时 / 告警联动**三种触发模式共用这一条链**。
 *
 * <p><b>核心约束（本类存在的理由）</b>：不新增任何直接执行通路。
 * 所有模式都只做两件事 —— 生成既有 {@link MultiExecService} 的预览，
 * 并把这次意图登记为 `PENDING_APPROVAL` 的执行记录。真正的执行必须由人
 * 通过既有 `/api/operations/multi-exec/execute` 提交预览 id 与确认码。</p>
 *
 * <p><b>为什么会话级运行连接是必需参数</b>：脚本要落到具体主机上执行，
 * 而目标主机的运行连接是用户会话内的资源。没有连接就无法生成预览 ——
 * 这不是限制，而是既有安全模型的正常要求。</p>
 */
@Service
public class SentinelScriptRunner {

    /** 三种触发模式。 */
    public static final String TRIGGER_MANUAL = "MANUAL";
    public static final String TRIGGER_SCHEDULE = "SCHEDULE";
    public static final String TRIGGER_ALERT = "ALERT";

    private final JdbcTemplate jdbc;
    private final MultiExecService multiExec;
    private final com.smartops.service.TeamAgentRunService teamRuns;
    private final Clock clock;

    public SentinelScriptRunner(JdbcTemplate jdbc, MultiExecService multiExec,
                                com.smartops.service.TeamAgentRunService teamRuns,
                                @org.springframework.beans.factory.annotation.Qualifier("mfaClock") Clock clock) {
        this.jdbc = jdbc;
        this.multiExec = multiExec;
        this.teamRuns = teamRuns;
        this.clock = clock;
    }

    /** 脚本事实（足够生成预览与授权判断）。 */
    private record ScriptFacts(long id, String name, String language, String riskLevel, boolean approved,
                               boolean enabled, int timeoutSec, int currentVersion) {}

    private ScriptFacts requireScript(long userId, long scriptId) {
        List<ScriptFacts> rows = jdbc.query("""
                SELECT id,name,language,risk_level,approved,enabled,timeout_sec,current_version
                  FROM sentinel_script WHERE id=? AND user_id=?
                """, (row, ignored) -> new ScriptFacts(row.getLong("id"), row.getString("name"),
                row.getString("language"), row.getString("risk_level"), row.getBoolean("approved"),
                row.getBoolean("enabled"), row.getInt("timeout_sec"), row.getInt("current_version")), scriptId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "脚本不存在或无权限访问");
        return rows.get(0);
    }

    private String currentBody(long scriptId, int version) {
        List<String> rows = jdbc.query("SELECT body FROM sentinel_script_version WHERE script_id=? AND version=?",
                (row, ignored) -> row.getString("body"), scriptId, version);
        if (rows.isEmpty()) throw new BusinessException(409, "脚本缺少可执行版本，请先保存一个版本");
        return rows.get(0);
    }

    /**
     * 准备一次执行：校验 → 变量替换 → 生成预览 → 登记待审批。
     *
     * @param trigger   MANUAL / SCHEDULE / ALERT
     * @param alertId   告警联动时的告警 id（其它模式为 null）
     * @param variables 平台变量（主机IP/告警指标/告警值…）
     */
    @Transactional
    public Map<String, Object> prepare(SessionUser actor, long scriptId, String trigger, List<String> runtimeIds,
                                       Long alertId, Map<String, String> variables) {
        long userId = requiredUser(actor);
        String normalizedTrigger = normalizeTrigger(trigger);
        ScriptFacts script = requireScript(userId, scriptId);
        if (!script.enabled()) throw new BusinessException(409, "脚本已停用，不能发起执行");
        if (runtimeIds == null || runtimeIds.isEmpty()) {
            throw new BusinessException(400, "至少选择一个目标主机（运行连接）");
        }

        String body = currentBody(script.id(), script.currentVersion());
        // 1) 高危预检：保存时已经拦过一次，执行前再拦一次（脚本可能被改过版本）
        var verdict = SentinelScriptLint.lint(body, script.language());
        if (!verdict.ok()) throw new BusinessException(400, "脚本未通过预检：" + verdict.detail());

        // 2) 平台变量替换（服务端权威，且拒绝含命令控制字符的值）
        SentinelVariables.Result substituted;
        try {
            substituted = SentinelVariables.applyChecked(body, variables);
        } catch (IllegalArgumentException unsafe) {
            throw new BusinessException(400, unsafe.getMessage());
        }
        if (!substituted.unresolved().isEmpty()) {
            throw new BusinessException(400, "脚本引用了未提供的变量：" + String.join("、", substituted.unresolved()));
        }

        // 3) 高危 / 未审批 / P0-P1 一律人工确认
        String severity = alertId == null ? null : alertSeverity(userId, alertId);
        boolean humanRequired = SentinelScriptLint.requiresApproval(script.riskLevel())
                || !script.approved()
                || "P0".equals(severity) || "P1".equals(severity);

        // 4) 生成既有链路的预览（唯一入口）
        MultiExecService.Preview preview = multiExec.preview(userId, substituted.body(), runtimeIds, false);

        // 5) 登记待审批执行记录；**不执行**
        Instant now = clock.instant();
        KeyHolder keys = new GeneratedKeyHolder();
        Map<String, String> vars = variables == null ? Map.of() : variables;
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("""
                    INSERT INTO sentinel_script_run(script_id,version,trigger_kind,alert_id,run_id,actor_id,
                        target_runtime,variables_json,started_at,result,output_excerpt)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """, java.sql.Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, script.id());
            statement.setInt(2, script.currentVersion());
            statement.setString(3, normalizedTrigger);
            if (alertId == null) statement.setNull(4, java.sql.Types.BIGINT); else statement.setLong(4, alertId);
            statement.setString(5, preview.id());
            statement.setLong(6, userId);
            statement.setString(7, String.join(",", runtimeIds));
            statement.setString(8, vars.isEmpty() ? null : toJson(vars));
            statement.setTimestamp(9, java.sql.Timestamp.from(now));
            statement.setString(10, "PENDING_APPROVAL");
            statement.setString(11, null);
            return statement;
        }, keys);

        if (alertId != null) {
            jdbc.update("UPDATE sentinel_alert SET status='PENDING_APPROVAL', recommended_script_id=? WHERE id=?",
                    script.id(), alertId);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("runId", generatedId(keys));
        result.put("previewId", preview.id());
        result.put("risk", preview.risk());
        result.put("requiredApprovals", preview.requiredApprovals());
        result.put("confirmationNonce", preview.confirmationNonce());
        result.put("humanApprovalRequired", humanRequired);
        result.put("trigger", normalizedTrigger);
        result.put("replacedVariables", substituted.replaced());
        result.put("nextStep", humanRequired
                ? "请人工核对预览内容后，带确认码提交既有多机执行接口：POST /api/operations/multi-exec/execute。"
                : "请带确认码提交既有多机执行接口：POST /api/operations/multi-exec/execute（仍需一次确认）。");
        result.put("note", "脚本库不直接执行命令；执行一律经既有预览—确认—执行链路。");
        return result;
    }

    /** 定时模式：到点只生成"待审批"，不自动执行。 */
    @Transactional
    public int fireDueSchedules() {
        Instant now = clock.instant();
        List<Map<String, Object>> due = jdbc.queryForList("""
                SELECT s.id,s.script_id,s.user_id,s.runtime_id,s.cron_expr
                  FROM sentinel_script_schedule s
                  JOIN sentinel_script c ON c.id=s.script_id
                 WHERE s.enabled=1 AND c.enabled=1
                   AND (s.next_fire_at IS NULL OR s.next_fire_at <= NOW())
                 ORDER BY s.id LIMIT 20
                """);
        int fired = 0;
        for (Map<String, Object> row : due) {
            long scheduleId = ((Number) row.get("id")).longValue();
            long scriptId = ((Number) row.get("script_id")).longValue();
            long userId = ((Number) row.get("user_id")).longValue();
            String runtimeId = (String) row.get("runtime_id");
            if (runtimeId == null || runtimeId.isBlank()) {
                // 没有绑定主机就不能凭空发起：跳过并记录原因，不假装执行过
                jdbc.update("UPDATE sentinel_script_schedule SET last_fire_at=NOW(), next_fire_at=NULL WHERE id=?", scheduleId);
                continue;
            }
            try {
                Map<String, String> variables = Map.of("时间", now.toString(), "脚本名", String.valueOf(scriptId));
                MultiExecService.Preview preview = multiExec.preview(userId, currentBody(scriptId, currentVersion(scriptId)),
                        List.of(runtimeId), false);
                jdbc.update("""
                        INSERT INTO sentinel_script_run(script_id,version,trigger_kind,run_id,actor_id,target_runtime,
                            variables_json,started_at,result)
                        VALUES(?,?,?,?,?,?,?,?,?)
                        """, scriptId, currentVersion(scriptId), TRIGGER_SCHEDULE, preview.id(), userId, runtimeId,
                        toJson(variables), java.sql.Timestamp.from(now), "PENDING_APPROVAL");
                jdbc.update("UPDATE sentinel_script_schedule SET last_fire_at=NOW(), next_fire_at=NULL WHERE id=?", scheduleId);
                fired++;
            } catch (RuntimeException failure) {
                // 单条失败不影响其它调度；保留 last_fire_at 变更以说明"尝试过"
                jdbc.update("UPDATE sentinel_script_schedule SET last_fire_at=NOW(), next_fire_at=NULL WHERE id=?", scheduleId);
            }
        }
        return fired;
    }

    /** 回填执行结果（由既有执行链的调用方在拿到真实结果后回填）。 */
    @Transactional
    public void recordResult(SessionUser actor, long runId, String result, Integer exitCode, Long durationMs, String outputExcerpt) {
        long userId = requiredUser(actor);
        Integer owned = jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_script_run WHERE id=? AND actor_id=?", Integer.class, runId, userId);
        if (owned == null || owned == 0) throw new BusinessException(404, "执行记录不存在或无权限访问");
        jdbc.update("""
                UPDATE sentinel_script_run SET result=?, exit_code=?, duration_ms=?, output_excerpt=?, finished_at=NOW()
                 WHERE id=? AND actor_id=?
                """, result, exitCode, durationMs, SentinelAlertLimits.truncate(outputExcerpt, 20000), runId, userId);
    }

    /**
     * 执行记录详情（回放用）。
     *
     * <p>刻意不含确认码：确认码是"一次性凭据"，只存在于 MultiExec 的预览里、
     * 从不写入执行记录。回放能看到的是"做了什么、结果如何"，不是"怎么再执行一次"。</p>
     */
    public Map<String, Object> runDetail(SessionUser actor, long runId) {
        long userId = requiredUser(actor);
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT r.id,r.script_id,c.name AS script_name,r.version,r.trigger_kind,r.alert_id,r.run_id,
                       r.actor_id,r.target_runtime,r.variables_json,r.started_at,r.finished_at,r.duration_ms,
                       r.exit_code,r.result,r.output_excerpt
                  FROM sentinel_script_run r JOIN sentinel_script c ON c.id=r.script_id
                 WHERE r.id=? AND c.user_id=?
                """, runId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "执行记录不存在或无权限访问");
        Map<String, Object> row = rows.get(0);
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("id", row.get("id"));
        detail.put("scriptId", row.get("script_id"));
        detail.put("scriptName", row.get("script_name"));
        detail.put("version", row.get("version"));
        detail.put("trigger", row.get("trigger_kind"));
        detail.put("alertId", row.get("alert_id"));
        detail.put("previewId", row.get("run_id"));
        detail.put("actorId", row.get("actor_id"));
        detail.put("targetRuntime", row.get("target_runtime"));
        detail.put("variables", parseVariables(row.get("variables_json")));
        detail.put("startedAt", String.valueOf(row.get("started_at")));
        detail.put("finishedAt", row.get("finished_at") == null ? null : String.valueOf(row.get("finished_at")));
        detail.put("durationMs", row.get("duration_ms"));
        detail.put("exitCode", row.get("exit_code"));
        detail.put("result", row.get("result"));
        detail.put("output", row.get("output_excerpt"));
        detail.put("replayNote", "回放展示的是这次执行的记录，不是重新执行；"
                + "确认码不落库，需要再次执行请重新生成预览并人工确认。");
        return detail;
    }

    private Map<String, Object> parseVariables(Object raw) {
        if (raw == null) return Map.of();
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().readValue(raw.toString(), Map.class);
        } catch (Exception malformed) {
            // JSON 坏了不影响回放：至少让人看到原始文本，而不是整页 500。
            return Map.of("raw", raw.toString());
        }
    }

    /* ── 协作优化 4：把告警处置接成团队 Agent 的受控工具 ───────────────── */

    /**
     * 由团队 Agent 提出处置建议（`propose-remediation` 工具的实现）。
     *
     * <p><b>它做了什么</b>：校验告警与脚本 → 生成 MultiExec 预览 → 在
     * {@code team_agent_run} 里创建一条 {@code PENDING_APPROVAL} 运行。</p>
     *
     * <p><b>它没有做什么</b>：不执行任何命令。运行进入待审批后，仍需另一位
     * 有审批权的成员 preview → approve，再由申请人 consumeGrant 执行。
     * 这条路径把"告警处置"接进了既有的团队协作凭据链，而不是新增一条执行通路。</p>
     *
     * <p><b>为什么需要已发布的 Agent 版本</b>：`TeamAgentRunService.create` 会校验
     * 版本一致性，避免"基于旧提示词的 Agent"发起处置。</p>
     */
    @Transactional
    public Map<String, Object> proposeRemediation(SessionUser actor, long teamId, long agentId, long versionId,
                                                  long alertId, long scriptId, String runtimeId) {
        long userId = requiredUser(actor);
        // 1) 告警必须属于当前用户，且脚本与运行连接都要可用
        String severity = alertSeverity(userId, alertId);
        ScriptFacts script = requireScript(userId, scriptId);
        if (!script.enabled()) throw new BusinessException(409, "脚本已停用，不能发起处置");
        if (runtimeId == null || runtimeId.isBlank()) {
            throw new BusinessException(400, "需要指定目标主机的运行连接");
        }

        // 2) 高危预检 + 变量替换（与手动/定时走同一套校验）
        String body = currentBody(script.id(), script.currentVersion());
        var verdict = SentinelScriptLint.lint(body, script.language());
        if (!verdict.ok()) throw new BusinessException(400, "脚本未通过预检：" + verdict.detail());
        Map<String, String> variables = Map.of("告警级别", severity,
                "告警指标", String.valueOf(alertMetric(userId, alertId)),
                "脚本名", script.name());
        SentinelVariables.Result substituted;
        try {
            substituted = SentinelVariables.applyChecked(body, variables);
        } catch (IllegalArgumentException unsafe) {
            throw new BusinessException(400, unsafe.getMessage());
        }

        // 3) 生成既有链路的预览（唯一执行入口）
        MultiExecService.Preview preview = multiExec.preview(userId, substituted.body(), List.of(runtimeId), false);

        // 4) 在团队侧创建待审批运行：这是"协作凭据"，不是执行
        Map<String, String> parameters = Map.of(
                "alertId", Long.toString(alertId),
                "scriptId", Long.toString(scriptId),
                "severity", severity);
        var run = teamRuns.create(actor, teamId, agentId, versionId, runtimeId, TOOL_ID, parameters);

        // 5) 登记执行记录并推进告警状态（仍等待审批）
        Instant now = clock.instant();
        jdbc.update("""
                INSERT INTO sentinel_script_run(script_id,version,trigger_kind,alert_id,run_id,actor_id,
                    target_runtime,variables_json,started_at,result)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """, script.id(), script.currentVersion(), TRIGGER_ALERT, alertId, preview.id(), userId,
                runtimeId, toJson(variables), java.sql.Timestamp.from(now), "PENDING_APPROVAL");
        jdbc.update("UPDATE sentinel_alert SET status='PENDING_APPROVAL', recommended_script_id=? WHERE id=?",
                script.id(), alertId);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("teamRunId", run.id());
        result.put("teamRunStatus", run.status());
        result.put("previewId", preview.id());
        result.put("confirmationNonce", preview.confirmationNonce());
        result.put("risk", preview.risk());
        result.put("requiredApprovals", preview.requiredApprovals());
        result.put("humanApprovalRequired", true);
        result.put("alertId", alertId);
        result.put("severity", severity);
        result.put("nextStep", "团队运行已创建为待审批。请由有审批权的成员 preview 后 approve，"
                + "再由申请人 consumeGrant 执行；哨兵不直接执行命令。");
        return result;
    }

    /** 工具标识，与 `OperationToolService` 中注册的一致。 */
    public static final String TOOL_ID = "propose-remediation";

    /* ── 定时计划 ─────────────────────────────────────────────────────── */

    public record ScheduleView(long id, long scriptId, String scriptName, String cronExpr, String runtimeId,
                               boolean enabled, String lastFireAt, String nextFireAt) {}

    public java.util.List<ScheduleView> listSchedules(SessionUser actor) {
        long userId = requiredUser(actor);
        return jdbc.query("""
                SELECT s.id,s.script_id,c.name AS script_name,s.cron_expr,s.runtime_id,s.enabled,s.last_fire_at,s.next_fire_at
                  FROM sentinel_script_schedule s JOIN sentinel_script c ON c.id=s.script_id
                 WHERE s.user_id=? ORDER BY s.id DESC LIMIT 100
                """, (row, ignored) -> new ScheduleView(row.getLong("id"), row.getLong("script_id"),
                row.getString("script_name"), row.getString("cron_expr"), row.getString("runtime_id"),
                row.getBoolean("enabled"),
                row.getTimestamp("last_fire_at") == null ? null : row.getTimestamp("last_fire_at").toInstant().toString(),
                row.getTimestamp("next_fire_at") == null ? null : row.getTimestamp("next_fire_at").toInstant().toString()),
                userId);
    }

    /**
     * 创建定时计划。
     *
     * <p>只保存"什么时候该发起"。到点后仍走 {@link #prepare} 同一条链 ——
     * 也就是说定时任务**不会自己执行**，它只会生成一条待审批的预览。</p>
     */
    @Transactional
    public ScheduleView createSchedule(SessionUser actor, long scriptId, String cronExpr, String runtimeId, Instant nextFireAt) {
        long userId = requiredUser(actor);
        requireScript(userId, scriptId);
        if (!SentinelVariables.validCron(cronExpr)) {
            throw new BusinessException(400, "定时表达式需为 5 段标准 cron，例如 */5 * * * *");
        }
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("""
                    INSERT INTO sentinel_script_schedule(script_id,user_id,cron_expr,runtime_id,enabled,next_fire_at)
                    VALUES(?,?,?,?,1,?)
                    """, java.sql.Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, scriptId);
            statement.setLong(2, userId);
            statement.setString(3, cronExpr.trim());
            statement.setString(4, runtimeId);
            statement.setTimestamp(5, nextFireAt == null ? null : java.sql.Timestamp.from(nextFireAt));
            return statement;
        }, keys);
        long id = generatedId(keys);
        return listSchedules(actor).stream().filter(item -> item.id() == id).findFirst()
                .orElseThrow(() -> new BusinessException(500, "创建后读取失败"));
    }

    @Transactional
    public void deleteSchedule(SessionUser actor, long id) {
        long userId = requiredUser(actor);
        Integer owned = jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_script_schedule WHERE id=? AND user_id=?",
                Integer.class, id, userId);
        if (owned == null || owned == 0) throw new BusinessException(404, "定时计划不存在或无权限访问");
        jdbc.update("DELETE FROM sentinel_script_schedule WHERE id=? AND user_id=?", id, userId);
    }

    /* ── 工具 ─────────────────────────────────────────────────────────── */

    private static long requiredUser(SessionUser actor) {
        if (actor == null || actor.id() == null) throw new BusinessException(401, "需要登录后使用脚本执行");
        return actor.id();
    }

    private static String normalizeTrigger(String trigger) {
        String text = trigger == null ? TRIGGER_MANUAL : trigger.trim().toUpperCase(java.util.Locale.ROOT);
        if (!List.of(TRIGGER_MANUAL, TRIGGER_SCHEDULE, TRIGGER_ALERT).contains(text)) {
            throw new BusinessException(400, "触发方式只能是 MANUAL、SCHEDULE 或 ALERT");
        }
        return text;
    }

    private String alertSeverity(long userId, long alertId) {
        List<String> rows = jdbc.query("""
                SELECT a.severity FROM sentinel_alert a
                  LEFT JOIN sentinel_task t ON t.id=a.task_id
                  LEFT JOIN sentinel_alert_rule r ON r.id=a.rule_id
                 WHERE a.id=? AND (t.user_id=? OR r.user_id=?)
                """, (row, ignored) -> row.getString("severity"), alertId, userId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "告警不存在或无权限访问");
        return rows.get(0);
    }

    /** 告警指标名，用于变量替换；查不到时返回占位符而不是让整次提议失败。 */
    private String alertMetric(long userId, long alertId) {
        List<String> rows = jdbc.query("""
                SELECT a.metric FROM sentinel_alert a
                  LEFT JOIN sentinel_task t ON t.id=a.task_id
                  LEFT JOIN sentinel_alert_rule r ON r.id=a.rule_id
                 WHERE a.id=? AND (t.user_id=? OR r.user_id=?)
                """, (row, ignored) -> row.getString("metric"), alertId, userId, userId);
        return rows.isEmpty() || rows.get(0) == null ? "unknown" : rows.get(0);
    }

    private int currentVersion(long scriptId) {
        Integer version = jdbc.queryForObject("SELECT current_version FROM sentinel_script WHERE id=?", Integer.class, scriptId);
        return version == null ? 1 : version;
    }

    private String toJson(Object value) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(value);
        } catch (Exception failure) {
            return null;
        }
    }

    private static long generatedId(KeyHolder keys) {
        var keyList = keys.getKeyList();
        if (keyList.isEmpty()) throw new BusinessException(500, "写入后未取得主键");
        Object id = keyList.get(0).get("id");
        if (id == null) {
            Object only = keyList.get(0).values().stream().findFirst().orElse(null);
            if (only == null) throw new BusinessException(500, "写入后未取得主键");
            return ((Number) only).longValue();
        }
        return ((Number) id).longValue();
    }
}
