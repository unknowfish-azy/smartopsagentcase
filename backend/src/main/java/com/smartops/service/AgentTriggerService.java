package com.smartops.service;

import com.smartops.diagnosis.AgentDiagnosisClient;
import com.smartops.dto.inspector.InspectionRecordRequest;
import com.smartops.exception.BusinessException;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * W7：事件驱动 —— Sentinel 告警触发的只读初诊与纠察写回。
 *
 * <p>链路：告警落库 → 5 分钟单资源防抖 → ai-service 只读诊断 → 写回 REVIEW 纠察事件。
 * 硬约束：</p>
 * <ul>
 *   <li>只读：诊断由 ai-service 固定只读白名单完成，本服务不执行任何写操作；</li>
 *   <li>模型不可用不产事件：ai-service 返回 {@code created=false} 时只记 WARN；</li>
 *   <li>防抖：同一资源键 5 分钟窗口内只触发一次（与 alert_correlation 同口径）；</li>
 *   <li>fail-open：任何异常都只记 WARN，不影响告警与调度主链路。</li>
 * </ul>
 */
@Slf4j
@Service
public class AgentTriggerService {

    private static final int QUEUE_CAPACITY = 32;
    private static final int PRUNE_THRESHOLD = 512;

    private final JdbcTemplate jdbcTemplate;
    private final InspectorEventService inspectorEventService;
    private final AgentDiagnosisClient diagnosisClient;
    private final boolean enabled;
    private final long windowMs;

    /** 资源键 → 最近一次触发时间；仅进程内，重启丢失可接受（防抖不是安全边界）。 */
    private final Map<String, Instant> lastTriggered = new ConcurrentHashMap<>();
    private final ExecutorService executor;

    public AgentTriggerService(
            JdbcTemplate jdbcTemplate,
            InspectorEventService inspectorEventService,
            AgentDiagnosisClient diagnosisClient,
            @Value("${smartops.agent.trigger.enabled:true}") boolean enabled,
            @Value("${smartops.agent.trigger.window-minutes:5}") long windowMinutes
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.inspectorEventService = inspectorEventService;
        this.diagnosisClient = diagnosisClient;
        this.enabled = enabled;
        this.windowMs = Duration.ofMinutes(Math.max(1, windowMinutes)).toMillis();
        this.executor = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(QUEUE_CAPACITY),
                runnable -> {
                    Thread thread = new Thread(runnable, "agent-trigger");
                    thread.setDaemon(true);
                    return thread;
                },
                discardOldest());
    }

    @PreDestroy
    public void shutdown() {
        executor.shutdownNow();
    }

    /**
     * Sentinel 告警落库后调用：防抖通过则异步触发一次只读初诊。
     *
     * <p>必须永不抛异常——调用方是告警主链路。</p>
     */
    public void onAlertCreated(TriggerContext context) {
        if (!enabled || context == null) return;
        try {
            if (!reserve(context.resourceKey(), Instant.now())) return;
            executor.execute(() -> diagnose(context));
        } catch (RuntimeException failure) {
            log.warn("agent_trigger.submit_failed alertId={} reason={}",
                    context.alertId(), failure.toString());
        }
    }

    /**
     * 内部端点入口：按 alertId 读取告警与归属后触发（防抖通过才受理）。
     *
     * @return 是否受理及原因，供内部调用方对账
     */
    public Map<String, Object> trigger(long alertId) {
        Map<String, Object> result = new LinkedHashMap<>();
        TriggerContext context = loadContext(alertId);
        if (!enabled) {
            result.put("triggered", false);
            result.put("reason", "TRIGGER_DISABLED");
            return result;
        }
        if (!reserve(context.resourceKey(), Instant.now())) {
            result.put("triggered", false);
            result.put("reason", "DEBOUNCED");
            result.put("resourceKey", context.resourceKey());
            return result;
        }
        try {
            executor.execute(() -> diagnose(context));
        } catch (RuntimeException failure) {
            result.put("triggered", false);
            result.put("reason", "SUBMIT_FAILED");
            log.warn("agent_trigger.submit_failed alertId={} reason={}", alertId, failure.toString());
            return result;
        }
        result.put("triggered", true);
        result.put("resourceKey", context.resourceKey());
        return result;
    }

    /* ── 防抖 ─────────────────────────────────────────────── */

    /** 同资源键窗口内只放行一次；package-private 便于单测。 */
    boolean reserve(String resourceKey, Instant now) {
        if (resourceKey == null || resourceKey.isBlank()) return true;
        Instant cutoff = now.minusMillis(windowMs);
        AtomicBoolean allowed = new AtomicBoolean(false);
        lastTriggered.compute(resourceKey, (key, previous) -> {
            if (previous == null || !previous.isAfter(cutoff)) {
                allowed.set(true);
                return now;
            }
            return previous;
        });
        if (lastTriggered.size() > PRUNE_THRESHOLD) {
            lastTriggered.entrySet().removeIf(entry -> entry.getValue().isBefore(cutoff));
        }
        return allowed.get();
    }

    /* ── 诊断与写回 ───────────────────────────────────────── */

    void diagnose(TriggerContext context) {
        try {
            Map<String, Object> payload = payload(context);
            Optional<Map<String, Object>> response = diagnosisClient.diagnose(payload);
            if (response.isEmpty()) {
                log.warn("agent_trigger.no_response alertId={}", context.alertId());
                return;
            }
            Map<String, Object> body = response.get();
            if (!Boolean.TRUE.equals(body.get("created"))) {
                // 模型不可用 / 被基线拦截 / 未运行：不产事件，只留 WARN。
                log.warn("agent_trigger.no_event alertId={} reason={} detail={}",
                        context.alertId(), body.get("reason"), body.get("detail"));
                return;
            }
            InspectionRecordRequest request = buildRecord(context, body);
            Map<String, Object> event = inspectorEventService.record(request, context.ownerUserId());
            log.info("agent_trigger.event_written alertId={} eventId={} runId={}",
                    context.alertId(), event.get("id"), body.get("runId"));
        } catch (RuntimeException failure) {
            log.warn("agent_trigger.diagnose_failed alertId={} reason={}",
                    context.alertId(), failure.toString());
        }
    }

    Map<String, Object> payload(TriggerContext context) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("alertId", context.alertId());
        putIfPresent(payload, "taskId", context.taskId());
        putIfPresent(payload, "resourceKey", context.resourceKey());
        putIfPresent(payload, "ownerUserId", context.ownerUserId() == null
                ? null : String.valueOf(context.ownerUserId()));
        putIfPresent(payload, "severity", context.severity());
        putIfPresent(payload, "metric", context.metric());
        putIfPresent(payload, "observed", context.observed());
        putIfPresent(payload, "threshold", context.threshold());
        putIfPresent(payload, "title", context.title());
        payload.put("source", "SENTINEL_ALERT");
        return payload;
    }

    /** 把只读诊断结果折算成 REVIEW 纠察事件（package-private 便于单测）。 */
    InspectionRecordRequest buildRecord(TriggerContext context, Map<String, Object> body) {
        String severity = mapSeverity(context.severity());
        String reason = describe(context);
        String recommendation = "请人工复核告警上下文后再决定处置；本次 AI 初诊仅执行只读查询，未执行任何写操作。";

        InspectionRecordRequest request = new InspectionRecordRequest();
        request.setTaskId("SENTINEL-" + context.alertId());
        request.setTarget(context.resourceKey());
        request.setStatus("REVIEW");
        request.setSeverity(severity);
        request.setCategory("SENTINEL_ALERT");
        request.setRequiresHuman(true);
        String answer = stringValue(body.get("answer"));
        request.setAgentClaim(answer.isBlank() ? "只读诊断完成，未形成文字结论。" : answer);
        request.setReason(reason);
        request.setRecommendation(recommendation);

        InspectionRecordRequest.Issue issue = new InspectionRecordRequest.Issue();
        issue.setCategory("SENTINEL_ALERT");
        issue.setSeverity(severity);
        issue.setReason(reason);
        issue.setRecommendation(recommendation);
        request.setIssues(List.of(issue));

        List<InspectionRecordRequest.Evidence> evidence = new ArrayList<>();
        evidence.add(evidence(context));
        Object brief = body.get("brief");
        if (brief instanceof Map<?, ?> briefMap && !briefMap.isEmpty()) {
            String note = stringValue(briefMap.get("narrative"));
            if (!note.isBlank()) {
                evidence.add(evidenceOf(note, "security_brief", 0.0));
            }
        }
        request.setEvidence(evidence);

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("source", "SENTINEL_ALERT");
        metadata.put("alertId", context.alertId());
        metadata.put("taskId", context.taskId());
        metadata.put("resourceKey", context.resourceKey());
        metadata.put("runId", body.get("runId"));
        metadata.put("modelAvailable", body.get("modelAvailable"));
        metadata.put("brief", body.get("brief"));
        metadata.put("toolCalls", body.get("toolCalls"));
        request.setMetadata(metadata);
        return request;
    }

    /* ── 数据读取 ─────────────────────────────────────────── */

    private TriggerContext loadContext(long alertId) {
        List<TriggerContext> rows = jdbcTemplate.query(
                "SELECT a.id, a.task_id, a.severity, a.metric, a.observed_value, "
                        + "a.threshold_value, a.title, t.user_id "
                        + "FROM sentinel_alert a LEFT JOIN sentinel_task t ON t.id = a.task_id "
                        + "WHERE a.id = ?",
                (row, index) -> new TriggerContext(
                        row.getLong("id"),
                        row.getObject("task_id", Long.class),
                        row.getObject("user_id", Long.class),
                        row.getString("severity"),
                        row.getString("metric"),
                        row.getString("observed_value"),
                        row.getString("threshold_value"),
                        row.getString("title"),
                        resourceKeyOf(row.getObject("task_id", Long.class), row.getLong("id"))),
                alertId);
        if (rows.isEmpty()) {
            throw new BusinessException(404, "告警不存在");
        }
        return rows.get(0);
    }

    private static String resourceKeyOf(Long taskId, long alertId) {
        return taskId == null ? "alert:" + alertId : "task:" + taskId;
    }

    /* ── 小工具 ───────────────────────────────────────────── */

    private static String describe(TriggerContext context) {
        StringBuilder text = new StringBuilder("哨兵告警 #").append(context.alertId());
        if (!isBlank(context.title())) text.append("：").append(context.title());
        if (!isBlank(context.metric())) {
            text.append("（").append(context.metric());
            if (!isBlank(context.observed())) text.append("=").append(context.observed());
            if (!isBlank(context.threshold())) text.append("，阈值 ").append(context.threshold());
            text.append("）");
        }
        return text.toString();
    }

    private static String mapSeverity(String raw) {
        String value = raw == null ? "" : raw.trim().toUpperCase();
        return switch (value) {
            case "P0" -> "CRITICAL";
            case "P1" -> "HIGH";
            case "P2" -> "WARN";
            case "P3" -> "INFO";
            case "CRITICAL", "HIGH", "WARN", "WARNING", "INFO" -> value;
            default -> "WARN";
        };
    }

    private static InspectionRecordRequest.Evidence evidence(TriggerContext context) {
        StringBuilder content = new StringBuilder("哨兵告警 #").append(context.alertId());
        if (!isBlank(context.title())) content.append("：").append(context.title());
        if (!isBlank(context.metric())) content.append("，").append(context.metric());
        if (!isBlank(context.observed())) content.append("=").append(context.observed());
        if (!isBlank(context.threshold())) content.append("（阈值 ").append(context.threshold()).append("）");
        return evidenceOf(content.toString(), "sentinel.alert", 1.0);
    }

    private static InspectionRecordRequest.Evidence evidenceOf(String content, String source, double score) {
        InspectionRecordRequest.Evidence item = new InspectionRecordRequest.Evidence();
        item.setContent(content.length() > 500 ? content.substring(0, 500) : content);
        item.setSource(source);
        item.setVersion("latest");
        item.setScore(score);
        return item;
    }

    private static void putIfPresent(Map<String, Object> target, String key, Object value) {
        if (value != null) target.put(key, value);
    }

    private static String stringValue(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private RejectedExecutionHandler discardOldest() {
        return (runnable, pool) -> {
            Runnable dropped = pool.getQueue().poll();
            if (dropped != null) {
                log.warn("agent_trigger.queue_full dropped_oldest");
            }
            pool.execute(runnable);
        };
    }

    /** 一次告警触发的上下文（Sentinel 与内部端点共用）。 */
    public record TriggerContext(
            long alertId,
            Long taskId,
            Long ownerUserId,
            String severity,
            String metric,
            String observed,
            String threshold,
            String title,
            String resourceKey
    ) { }
}
