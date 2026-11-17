package com.smartops.sentinel;

import com.smartops.service.OperatorMemoryService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * 经验蒸馏：处置脚本执行结束后，把成功/失败的因果链自动沉淀进 OperatorMemory。
 *
 * <p><b>蒸馏时机</b>：{@link SentinelScriptRunner#recordResult} 写回执行结果之后。
 * 只有当脚本 result 是 {@code SUCCESS} 或 {@code FAILED}（最终态）时才蒸馏 ——
 * PENDING_APPROVAL / RUNNING / CANCELLED 等中间态或非最终态直接跳过。</p>
 *
 * <p><b>沉淀内容</b>：因果链（什么告警 + 用了什么脚本 + 结果如何）+ 可执行规则。
 * 格式：</p>
 * <pre>
 *   incident_key = "sentinel:{metric}:{severity}"
 *   preferred_action = "{script.name}（成功/失败）→ 下次遇到 {metric} {severity} 用此脚本"
 *   source_refs = "SCRIPT_RUN:{runId}"   ← 幂等键
 *   memory_type = "DECISION_LOOP"        ← 与既有 DecisionLoop 沉淀同类型
 * </pre>
 *
 * <p><b>降级保护</b>：</p>
 * <ul>
 *   <li>trigger_kind 不是 {@code ALERT} → 不蒸馏（手动/定时触发不算"告警处置"）；</li>
 *   <li>脚本名或告警指标缺失 → 跳过；</li>
 *   <li>OperatorMemoryService 抛错 → 日志记录后静默（主链路不能因为蒸馏挂）；</li>
 *   <li>source_refs 唯一键冲突 → OperatorMemoryService 自己幂等返回已有行。</li>
 * </ul>
 */
@Slf4j
@Service
public class DistillExperienceService {

    private final JdbcTemplate jdbc;
    private final OperatorMemoryService memories;

    /** 只接受这两种最终态作为蒸馏信号。 */
    private static final List<String> FINAL_RESULTS = List.of("SUCCESS", "FAILED");

    @Value("${smartops.sentinel.distill.enabled:true}")
    private boolean enabled = true;

    public DistillExperienceService(JdbcTemplate jdbc, OperatorMemoryService memories) {
        this.jdbc = jdbc;
        this.memories = memories;
    }

    /**
     * 处置执行结果落库后调用，尝试蒸馏一条经验。
     *
     * @param runId sentinel_script_run.id
     */
    public void distillAfterRun(long runId) {
        if (!enabled) return;
        try {
            RunSnapshot snap = loadRunSnapshot(runId);
            if (snap == null) return;
            // 只蒸馏告警触发的处置
            if (!"ALERT".equalsIgnoreCase(snap.triggerKind())) return;
            // 只接受最终态
            if (!FINAL_RESULTS.contains(snap.result().toUpperCase())) return;
            // 基本字段缺失就跳过
            if (snap.alertId() == null || snap.scriptName() == null
                    || snap.metric() == null || snap.metric().isBlank()) return;

            // 幂等键：SCRIPT_RUN:{runId}
            String sourceRefs = "SCRIPT_RUN:" + runId;
            // incident_key：sentinel:{metric}:{severity}
            String incidentKey = "sentinel:" + snap.metric().toLowerCase()
                    + (snap.severity() != null ? ":" + snap.severity() : "");
            // preferred_action：因果链 + 可执行规则
            String outcome = "SUCCESS".equalsIgnoreCase(snap.result()) ? "成功" : "失败";
            String action = buildAction(snap, outcome);

            OperatorMemoryService.Memory created = memories.recordLearned(
                    snap.userId(), incidentKey, action, sourceRefs);
            if (created != null) {
                log.info("Distilled sentinel experience: run={} metric={} severity={} outcome={} memoryId={}",
                        runId, snap.metric(), snap.severity(), outcome, created.id());
            }
        } catch (RuntimeException pe) {
            // 蒸馏失败不影响主链路
            log.debug("Distill skipped for run {}: {}", runId, pe.getMessage());
        }
    }

    /** 因果链文案：什么告警 + 用了什么脚本 + 结果如何 → 下次遇到 X 用 Y。 */
    private String buildAction(RunSnapshot snap, String outcome) {
        StringBuilder text = new StringBuilder();
        text.append("指标 ").append(snap.metric());
        if (snap.severity() != null) text.append("（").append(snap.severity()).append("级）");
        text.append(" 触发告警后使用脚本「").append(snap.scriptName()).append("」处置").append(outcome);
        String note = outcome.equals("成功")
                ? "→ 下次遇到同类指标告警可优先考虑"
                : "→ 该脚本对此类告警可能无效或有问题";
        text.append("。").append(note).append("。");
        return text.toString();
    }

    /* ── 内部 helpers ─────────────────────────────────────────────────────── */

    private RunSnapshot loadRunSnapshot(long runId) {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT r.id, r.trigger_kind, r.result, r.actor_id, r.alert_id,
                       c.name AS script_name,
                       a.metric, a.severity
                  FROM sentinel_script_run r
                  JOIN sentinel_script c ON c.id = r.script_id
                  LEFT JOIN sentinel_alert a ON a.id = r.alert_id
                 WHERE r.id = ?
                """, runId);
        if (rows.isEmpty()) return null;
        Map<String, Object> row = rows.get(0);
        Object severityObj = row.get("severity");
        return new RunSnapshot(
                (String) row.get("trigger_kind"),
                (String) row.get("result"),
                row.get("actor_id") != null ? ((Number) row.get("actor_id")).longValue() : null,
                row.get("alert_id") != null ? ((Number) row.get("alert_id")).longValue() : null,
                (String) row.get("script_name"),
                (String) row.get("metric"),
                severityObj != null ? severityObj.toString() : null);
    }

    /** sentinel_script_run 完整快照（蒸馏一次性读完）。 */
    private record RunSnapshot(String triggerKind, String result, Long userId, Long alertId,
                               String scriptName, String metric, String severity) {}
}
