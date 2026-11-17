package com.smartops.sentinel;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 告警关联服务：把同时密集触发的告警折叠成一个事件，并标注根因候选与关联度。
 *
 * <p>在线折叠（fireAlert 后调用）：</p>
 * <ol>
 *   <li>用 resourceKey（如 "server-1"）查最近 correlation event；</li>
 *   <li>在 event 的时间窗内、同 resource 的 OPEN 告警归并进来；</li>
 *   <li>无可用 event → 新建（窗口 windowMinutes 分钟，默认 5）；</li>
 *   <li>更新 root_cause_alert_id（event 内最早 fired_at）。</li>
 * </ol>
 *
 * <p>离线 lift 关联（定时任务调用）：</p>
 * <ul>
 *   <li>从历史 sentinel_alert 聚合 metric 对的 co-fire 次数；</li>
 *   <li>lift = P(A|B) / P(A)，>1 说明正相关（一起炸的概率比随机高）。</li>
 * </ul>
 */
@Slf4j
@Service
public class AlertCorrelationService {

    private final JdbcTemplate jdbc;
    private final ObjectMapper om = new ObjectMapper();

    @Value("${smartops.sentinel.correlation.enabled:true}")
    private boolean enabled = true;

    /** 关联事件折叠窗口（分钟）。同一窗口内、同 resourceKey 的告警归并为一个事件。 */
    @Value("${smartops.sentinel.correlation.window-minutes:5}")
    private int windowMinutes = 5;

    /** 新建事件窗口向未来的偏移（分钟）。让后续几秒内的告警也能并入。 */
    @Value("${smartops.sentinel.correlation.future-buffer-minutes:1}")
    private int futureBufferMinutes = 1;

    /** 事件存活时长（分钟）。超过这个时长不再并入新告警。 */
    @Value("${smartops.sentinel.correlation.event-ttl-minutes:30}")
    private int eventTtlMinutes = 30;

    public AlertCorrelationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 单条告警触发关联折叠。返回它所属的 correlation event（可能是新建或更新已有）。 */
    public CorrelationResult foldAlert(long alertId, long taskId, String metric, String severity, String observed,
                                       Instant firedAt) {
        if (!enabled) return new CorrelationResult(null, false);

        // 1) 从 sentinel_task 拿 resourceKey（如果 task 有 resource_id 或 server 字段；没有就用 task_id 兜底）
        String resourceKey = resolveResourceKey(taskId);

        // 2) 查最近可用的 correlation event
        var existing = jdbc.query(
                "SELECT id, window_start, window_end FROM sentinel_alert_correlation "
                        + "WHERE resource_key=? AND status='OPEN' "
                        + "AND window_end >= ? AND window_start <= ? "
                        + "ORDER BY window_start DESC LIMIT 1",
                (rs, n) -> new long[] { rs.getLong("id"),
                        rs.getTimestamp("window_start").getTime(),
                        rs.getTimestamp("window_end").getTime() },
                resourceKey,
                java.sql.Timestamp.from(firedAt.minus(Duration.ofMinutes(windowMinutes))),
                java.sql.Timestamp.from(firedAt.plus(Duration.ofMinutes(futureBufferMinutes))));

        long corrId;
        boolean created;
        if (existing.isEmpty()) {
            corrId = createEvent(resourceKey, firedAt, alertId, metric, severity);
            created = true;
        } else {
            corrId = existing.get(0)[0];
            created = false;
        }

        // 3) 关联告警到 event
        try {
            jdbc.update("UPDATE sentinel_alert SET correlation_id=?, correlation_group=? WHERE id=?",
                    corrId, "corr:" + corrId, alertId);
        } catch (RuntimeException ex) {
            // 旧表可能还没这俩列（Flyway 还没跑），静默跳过
            log.debug("correlation columns missing on sentinel_alert, skip: {}", ex.getMessage());
        }

        // 4) 更新 event 聚合（metric 列表、task 列表、severity、root_cause、summary）
        refreshEvent(corrId, resourceKey);
        return new CorrelationResult(corrId, created);
    }

    /** 离线：计算 lift 关联度。从历史 OPEN/RESOLVED 告警算 metric 对的共现。 */
    public int computeLiftCorrelations() {
        if (!enabled) return 0;
        var alerts = jdbc.query(
                "SELECT task_id, metric FROM sentinel_alert WHERE fired_at >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 7 DAY) "
                        + "AND metric IS NOT NULL AND status <> 'ACKNOWLEDGED'",
                (rs, n) -> new String[] { String.valueOf(rs.getLong("task_id")), rs.getString("metric") });

        if (alerts.size() < 3) return 0;

        // 同一 task 的 metric 共现 → 建 metric 对的 co-fire 计数
        Map<String, Integer> coFires = new HashMap<>();  // "a|b" → count
        Map<String, Integer> single = new HashMap<>();   // metric → count
        Map<Long, Set<String>> taskMetrics = new HashMap<>();
        for (String[] a : alerts) {
            taskMetrics.computeIfAbsent(Long.parseLong(a[0]), k -> new HashSet<>()).add(a[1]);
            single.merge(a[1], 1, Integer::sum);
        }
        for (Set<String> set : taskMetrics.values()) {
            List<String> list = new ArrayList<>(set);
            for (int i = 0; i < list.size(); i++) {
                single.merge(list.get(i), 1, Integer::sum);
                for (int j = i + 1; j < list.size(); j++) {
                    String key = smallerFirst(list.get(i), list.get(j));
                    coFires.merge(key, 1, Integer::sum);
                }
            }
        }

        // lift = P(A|B) / P(A) = coFire(A,B) * N / (count(A) * count(B))
        int n = alerts.size();
        int edges = 0;
        for (Map.Entry<String, Integer> e : coFires.entrySet()) {
            String[] pair = e.getKey().split("\\|");
            int aCount = single.getOrDefault(pair[0], 1);
            int bCount = single.getOrDefault(pair[1], 1);
            double lift = (e.getValue() * (double) n) / ((double) aCount * bCount);
            // 写入 correlation_edge（更新已有的，没有就插入）
            jdbc.update("UPDATE sentinel_alert_correlation_edge SET co_fires=?, lift_score=? "
                    + "WHERE metric_a=? AND metric_b=? AND correlation_type='LIFT'",
                    e.getValue(), lift, pair[0], pair[1]);
            int updated = jdbc.update("SELECT ROW_COUNT()", new Object[] {});
            if (updated != 1) {
                // INSERT (id 用 0 让数据库自增)
                jdbc.update("INSERT IGNORE INTO sentinel_alert_correlation_edge "
                        + "(correlation_id, alert_a_id, alert_b_id, metric_a, metric_b, co_fires, lift_score, correlation_type) "
                        + "VALUES(0,0,0,?,?,?,?,?)",
                        pair[0], pair[1], e.getValue(), lift, "LIFT");
            }
            edges++;
        }
        log.info("lift correlation computed: {} metric pairs from {} alerts", edges, n);
        return edges;
    }

    /* ── 内部 ───────────────────────────────────────── */

    private String resolveResourceKey(long taskId) {
        // 预留：sentinel_task 加 resource_id 字段后用它。当前用 task_id 兜底（每个 task 自带唯一资源键）
        return "task:" + taskId;
    }

    private long createEvent(String resourceKey, Instant now, long alertId, String metric, String severity) {
        String key = "corr:" + resourceKey + ":" + now.getEpochSecond() / 60;
        java.sql.Timestamp start = java.sql.Timestamp.from(now.minus(Duration.ofMinutes(1)));
        java.sql.Timestamp end = java.sql.Timestamp.from(now.plus(Duration.ofMinutes(windowMinutes)));

        // 先查是否已存在（同分钟同资源，去重）
        var existing = jdbc.query(
                "SELECT id FROM sentinel_alert_correlation WHERE `key`=?",
                (rs, n) -> rs.getLong("id"), key);
        if (!existing.isEmpty()) return existing.get(0);

        jdbc.update("INSERT INTO sentinel_alert_correlation(`key`,resource_key,window_start,window_end,"
                        + "alert_count,root_cause_alert_id,root_cause_metric,severity,status)"
                        + " VALUES(?,?,?,?,?,?,?,?,?)",
                key, resourceKey, start, end, 1, alertId, metric, severity, "OPEN");

        // 如果 severity 还需要合并提升（P2 → P1 当已有 P1），这里留接口；新建事件直接用当前告警 severity
        var ids = jdbc.query("SELECT id FROM sentinel_alert_correlation WHERE `key`=?",
                (rs, n) -> rs.getLong("id"), key);
        return ids.get(0);
    }

    private void refreshEvent(long corrId, String resourceKey) {
        try {
            // 聚合：count、metrics、task_ids、severity（最高）、root_cause（最早 fired_at）
            var agg = jdbc.query(
                    "SELECT COUNT(*) cnt, MIN(fired_at) first_at FROM sentinel_alert "
                            + "WHERE correlation_id=? AND status<>'RESOLVED' AND status<>'CLOSED'",
                    (rs, n) -> new Object[] { rs.getInt("cnt"),
                            rs.getTimestamp("first_at") == null ? null : rs.getTimestamp("first_at").getTime() },
                    corrId).stream().findFirst().orElse(new Object[] {0, null});

            int cnt = (Integer) agg[0];
            Long firstAt = (Long) agg[1];

            // metrics + task_ids 去重列表
            var metricsRows = jdbc.query(
                    "SELECT DISTINCT metric FROM sentinel_alert WHERE correlation_id=? AND metric IS NOT NULL",
                    (rs, n) -> rs.getString("metric"), corrId);
            var taskRows = jdbc.query(
                    "SELECT DISTINCT task_id FROM sentinel_alert WHERE correlation_id=?",
                    (rs, n) -> rs.getLong("task_id"), corrId);

            // severity 取最高（P0 > P1 > P2 > P3）
            var sevRows = jdbc.query(
                    "SELECT DISTINCT severity FROM sentinel_alert WHERE correlation_id=? AND severity IS NOT NULL ORDER BY severity",
                    (rs, n) -> rs.getString("severity"), corrId);
            String severity = pickWorst(sevRows);

            // root cause：最早 fired_at 那条
            var root = jdbc.query(
                    "SELECT id, metric FROM sentinel_alert WHERE correlation_id=? AND fired_at=? LIMIT 1",
                    (rs, n) -> new Object[] { rs.getLong("id"), rs.getString("metric") },
                    corrId, firstAt == null ? null : new java.sql.Timestamp(firstAt)).stream().findFirst().orElse(null);
            Long rootId = root == null ? null : (Long) root[0];
            String rootMetric = root == null ? null : (String) root[1];

            // summary：简洁描述
            String summary = buildSummary(metricsRows, taskRows, severity, rootMetric);

            jdbc.update("UPDATE sentinel_alert_correlation SET alert_count=?, root_cause_alert_id=?, root_cause_metric=?, "
                            + "severity=?, metrics_affected=?, task_ids=?, summary=? WHERE id=?",
                    cnt, rootId, rootMetric, severity,
                    toJson(metricsRows), toJson(taskRows), summary, corrId);
        } catch (RuntimeException ex) {
            log.debug("refreshEvent failed for corrId={}: {}", corrId, ex.getMessage());
        }
    }

    /* ── 小工具 ────────────────────────────────────── */

    private static String pickWorst(List<String> severities) {
        String[] order = {"P0", "P1", "P2", "P3"};
        for (String o : order) if (severities.contains(o)) return o;
        return severities.isEmpty() ? "P2" : severities.get(0);
    }

    private String buildSummary(List<String> metrics, List<Long> tasks, String severity, String rootMetric) {
        if (metrics.isEmpty()) return severity + " 告警风暴";
        // "CPU+内存+IO 同时越界" 或 "多指标告警"
        StringBuilder sb = new StringBuilder();
        int take = Math.min(3, metrics.size());
        for (int i = 0; i < take; i++) {
            if (i > 0) sb.append("+");
            sb.append(metrics.get(i));
        }
        if (metrics.size() > take) sb.append(" 等").append(metrics.size());
        sb.append(" 同时越界");
        if (rootMetric != null && !Objects.equals(rootMetric, metrics.isEmpty() ? null : metrics.get(0))) {
            sb.append("（根因候选：").append(rootMetric).append("）");
        }
        return sb.toString();
    }

    private String toJson(Object obj) {
        try { return om.writeValueAsString(obj); }
        catch (JsonProcessingException e) { return "[]"; }
    }

    private static String smallerFirst(String a, String b) {
        return a.compareTo(b) <= 0 ? a + "|" + b : b + "|" + a;
    }

    /** foldAlert 返回值。 */
    public record CorrelationResult(Long correlationId, boolean eventCreated) {}
}
