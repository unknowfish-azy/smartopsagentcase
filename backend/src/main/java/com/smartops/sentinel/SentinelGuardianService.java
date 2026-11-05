package com.smartops.sentinel;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.service.IncidentRecommendationService;
import com.smartops.service.OperatorMemoryService;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 哨兵守护 Agent：告警触发后自动取证，并从历史样本持续学习指标基线。
 *
 * <p>两条硬约束：
 * <ol>
 *   <li>只读。取证只查库，不执行脚本、不改告警状态；</li>
 *   <li>学习只给建议。基线学出来的是 {@code suggested_threshold}，
 *       必须人工确认后才写回阈值模板，绝不自动改生产阈值。</li>
 * </ol>
 */
@Service
@RequiredArgsConstructor
public class SentinelGuardianService {

    /** 参与基线统计的最近样本数。 */
    private static final int BASELINE_WINDOW = 200;
    /** 样本太少时不做结论，避免刚上线就"学"出错误基线。 */
    private static final int MIN_SAMPLES = 20;
    /** 建议值与原阈值偏差小于该比例时视为稳定，不打扰人。 */
    private static final double SUGGEST_RATIO = 0.1d;

    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    private final OperatorMemoryService memories;
    private final IncidentRecommendationService recommendations;

    /* ── 告警取证 ─────────────────────────────────────────────── */

    /** 为新告警补充证据；每个告警只做一次，已取证的不重复跑。 */
    @Transactional
    public int enrichPending(int limit) {
        List<Long> alertIds = jdbc.queryForList(
                "SELECT a.id FROM sentinel_alert a JOIN sentinel_task t ON t.id = a.task_id "
                        + "WHERE NOT EXISTS (SELECT 1 FROM sentinel_guardian_evidence e WHERE e.alert_id = a.id) "
                        + "ORDER BY a.fired_at DESC LIMIT ?",
                Long.class, Math.max(1, Math.min(limit, 50)));
        int enriched = 0;
        for (Long alertId : alertIds) {
            try {
                enrich(alertId);
                enriched++;
            } catch (RuntimeException failure) {
                // 单条告警取证失败不能影响其它告警，也不能影响轮询线程。
            }
        }
        return enriched;
    }

    /** 手工重新取证：先清旧证据再生成，保证结果反映当前数据。 */
    @Transactional
    public Map<String, Object> collect(long userId, long alertId) {
        requireOwnedAlert(userId, alertId);
        jdbc.update("DELETE FROM sentinel_guardian_evidence WHERE alert_id = ?", alertId);
        enrich(alertId);
        return Map.of("alertId", alertId, "evidence", evidenceOf(alertId));
    }

    private void enrich(long alertId) {
        Map<String, Object> alert = alertRow(alertId);
        long userId = ((Number) alert.get("userId")).longValue();
        long taskId = ((Number) alert.get("taskId")).longValue();
        String metric = str(alert.get("metric"));
        String severity = str(alert.get("severity"));
        String title = str(alert.get("title"));
        String observed = str(alert.get("observedValue"));
        String threshold = str(alert.get("thresholdValue"));

        // 1) 指标基线：近 N 个样本的均值、P95、区间。
        Stats stats = stats(taskId, metric);
        if (stats.count() > 0) {
            insertEvidence(userId, alertId, "BASELINE", "指标基线（最近 " + stats.count() + " 个样本）",
                    String.format(Locale.ROOT, "均值 %.2f · P95 %.2f · 区间 %.2f ~ %.2f",
                            stats.avg(), stats.p95(), stats.min(), stats.max()));
        } else {
            insertEvidence(userId, alertId, "BASELINE", "指标基线", "该指标暂无历史数值样本，无法形成基线");
        }

        // 2) 同类告警：最近 7 天同一任务同一指标的重复次数。
        Long related = jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_alert WHERE task_id=? AND metric=? AND id<>?",
                Long.class, taskId, metric, alertId);
        Timestamp lastFired = jdbc.queryForObject(
                "SELECT MAX(fired_at) FROM sentinel_alert WHERE task_id=? AND metric=? AND id<>?",
                Timestamp.class, taskId, metric, alertId);
        insertEvidence(userId, alertId, "RELATED_ALERT", "同类告警 " + (related == null ? 0 : related) + " 条",
                lastFired == null ? "此前没有同指标告警，属于首次出现" : "最近一次同指标告警：" + lastFired.toLocalDateTime());

        // 3) 运维记忆：复用与告警研判同一份记忆，避免两套建议互相矛盾。
        var pattern = new IncidentRecommendationService.IncidentPattern(
                metric, title, severity, List.of("观测值 " + observed + "，阈值 " + threshold));
        var matches = recommendations.recommend(pattern, memories.list(userId));
        for (var match : matches.stream().limit(3).toList()) {
            insertEvidence(userId, alertId, "MEMORY", match.action(),
                    "置信度 " + Math.round(match.confidence() * 100) + "% · 来源 " + match.source());
        }
    }

    private void insertEvidence(long userId, long alertId, String kind, String title, String detail) {
        jdbc.update("INSERT INTO sentinel_guardian_evidence(user_id,alert_id,kind,title,detail,created_at) VALUES(?,?,?,?,?,?)",
                userId, alertId, kind, truncate(title, 255), truncate(detail, 800), LocalDateTime.now());
    }

    /* ── 持续学习 ─────────────────────────────────────────────── */

    /**
     * 扫描所有启用中的哨兵任务，按指标学习基线并生成阈值建议。
     *
     * @return 产生建议或更新的基线数量
     */
    @Transactional
    public int learnAll() {
        List<Map<String, Object>> tasks = jdbc.queryForList(
                "SELECT id,user_id,name,template_id FROM sentinel_task WHERE enabled=1 AND template_id IS NOT NULL");
        int learned = 0;
        for (Map<String, Object> task : tasks) {
            long taskId = ((Number) task.get("id")).longValue();
            long userId = ((Number) task.get("user_id")).longValue();
            String taskName = str(task.get("name"));
            for (Rule rule : readRules(templateRules(((Number) task.get("template_id")).longValue()))) {
                if (learnOne(userId, taskId, taskName, rule)) learned++;
            }
        }
        return learned;
    }

    private boolean learnOne(long userId, long taskId, String taskName, Rule rule) {
        Stats stats = stats(taskId, rule.metric());
        if (stats.count() < MIN_SAMPLES) return false;

        double suggested = suggest(rule, stats);
        double diff = Math.abs(suggested - rule.value()) / Math.max(Math.abs(rule.value()), 1e-6);
        if (diff < SUGGEST_RATIO) {
            // 基线稳定：保留已有结论，不反复生成噪声。
            return upsertProfile(userId, taskId, taskName, rule, stats, suggested, "STABLE");
        }
        return upsertProfile(userId, taskId, taskName, rule, stats, suggested, "SUGGESTED");
    }

    private double suggest(Rule rule, Stats stats) {
        double base = switch (rule.operator()) {
            case "lt", "lte" -> stats.p05() * 0.85d;
            default -> stats.p95() * 1.15d;
        };
        return Math.round(base * 100d) / 100d;
    }

    private boolean upsertProfile(long userId, long taskId, String taskName, Rule rule, Stats stats,
                                  double suggested, String status) {
        List<Long> existing = jdbc.queryForList(
                "SELECT id FROM sentinel_learning_profile WHERE user_id=? AND task_id=? AND metric=?",
                Long.class, userId, taskId, rule.metric());
        LocalDateTime now = LocalDateTime.now();
        if (existing.isEmpty()) {
            jdbc.update("INSERT INTO sentinel_learning_profile"
                            + "(user_id,task_id,task_name,metric,operator,sample_count,avg_value,p95_value,min_value,max_value,"
                            + "current_threshold,suggested_threshold,status,learned_at,updated_at)"
                            + " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    userId, taskId, taskName, rule.metric(), rule.operator(), stats.count(), stats.avg(), stats.p95(),
                    stats.min(), stats.max(), rule.value(), suggested, status, now, now);
            return true;
        }
        jdbc.update("UPDATE sentinel_learning_profile SET task_name=?,operator=?,sample_count=?,avg_value=?,p95_value=?,"
                        + "min_value=?,max_value=?,current_threshold=?,suggested_threshold=?,status=?,learned_at=?,updated_at=? "
                        + "WHERE id=?",
                taskName, rule.operator(), stats.count(), stats.avg(), stats.p95(), stats.min(), stats.max(),
                rule.value(), suggested, status, now, now, existing.get(0));
        return true;
    }

    /** 人工确认后把建议阈值写回任务绑定的阈值模板。 */
    @Transactional
    public Map<String, Object> apply(long userId, long profileId) {
        Map<String, Object> profile = requireProfile(userId, profileId);
        long taskId = ((Number) profile.get("taskId")).longValue();
        List<Long> templateIds = jdbc.queryForList("SELECT template_id FROM sentinel_task WHERE id=? AND user_id=?",
                Long.class, taskId, userId);
        if (templateIds.isEmpty() || templateIds.get(0) == null) {
            throw new BusinessException("该任务没有绑定阈值模板，无法应用建议");
        }
        long templateId = templateIds.get(0);
        String raw = templateRules(templateId);
        List<Map<String, Object>> rules = readRawRules(raw);
        String metric = str(profile.get("metric"));
        double suggested = ((Number) profile.get("suggestedThreshold")).doubleValue();
        boolean replaced = false;
        for (Map<String, Object> rule : rules) {
            if (metric.equals(str(rule.get("metric")))) {
                rule.put("value", suggested);
                replaced = true;
            }
        }
        if (!replaced) throw new BusinessException("阈值模板中不存在指标 " + metric + " 的规则");

        try {
            jdbc.update("UPDATE sentinel_threshold_template SET rules_json=?,updated_at=? WHERE id=? AND user_id=?",
                    json.writeValueAsString(rules), LocalDateTime.now(), templateId, userId);
        } catch (com.fasterxml.jackson.core.JsonProcessingException failure) {
            throw new BusinessException("阈值模板序列化失败");
        }
        jdbc.update("UPDATE sentinel_learning_profile SET status='APPLIED',applied_at=?,updated_at=? WHERE id=?",
                LocalDateTime.now(), LocalDateTime.now(), profileId);
        return profile;
    }

    @Transactional
    public void dismiss(long userId, long profileId) {
        requireProfile(userId, profileId);
        jdbc.update("UPDATE sentinel_learning_profile SET status='DISMISSED',updated_at=? WHERE id=?",
                LocalDateTime.now(), profileId);
    }

    /* ── 查询 ────────────────────────────────────────────────── */

    public List<Map<String, Object>> listProfiles(long userId) {
        return jdbc.queryForList(
                        "SELECT id,task_id,task_name,metric,operator,sample_count,avg_value,p95_value,min_value,max_value,"
                                + "current_threshold,suggested_threshold,status,learned_at,applied_at "
                                + "FROM sentinel_learning_profile WHERE user_id=? ORDER BY status='SUGGESTED' DESC, updated_at DESC",
                        userId)
                .stream().map(this::camelize).toList();
    }

    public List<Map<String, Object>> listEvidence(long userId, int limit) {
        return jdbc.queryForList(
                        "SELECT e.id,e.alert_id,e.kind,e.title,e.detail,e.created_at,a.title AS alert_title,"
                                + "a.severity,a.status AS alert_status,t.name AS task_name "
                                + "FROM sentinel_guardian_evidence e "
                                + "JOIN sentinel_alert a ON a.id=e.alert_id "
                                + "LEFT JOIN sentinel_task t ON t.id=a.task_id "
                                + "WHERE e.user_id=? ORDER BY e.created_at DESC, e.id DESC LIMIT ?",
                        userId, Math.max(1, Math.min(limit, 200)))
                .stream().map(this::camelize).toList();
    }

    public Map<String, Object> stats(long userId) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("profiles", count(userId, "SELECT COUNT(*) FROM sentinel_learning_profile WHERE user_id=?"));
        result.put("suggested", count(userId, "SELECT COUNT(*) FROM sentinel_learning_profile WHERE user_id=? AND status='SUGGESTED'"));
        result.put("applied", count(userId, "SELECT COUNT(*) FROM sentinel_learning_profile WHERE user_id=? AND status='APPLIED'"));
        result.put("evidence", count(userId, "SELECT COUNT(*) FROM sentinel_guardian_evidence WHERE user_id=?"));
        return result;
    }

    private long count(long userId, String sql) {
        Long value = jdbc.queryForObject(sql, Long.class, userId);
        return value == null ? 0 : value;
    }

    /* ── 内部数据 ────────────────────────────────────────────── */

    private Map<String, Object> alertRow(long alertId) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT a.id,a.task_id,a.severity,a.title,a.metric,a.observed_value,a.threshold_value,t.user_id "
                        + "FROM sentinel_alert a JOIN sentinel_task t ON t.id=a.task_id WHERE a.id=?",
                alertId);
        if (rows.isEmpty()) throw new BusinessException(404, "告警不存在或缺关联哨兵任务");
        return camelize(rows.get(0));
    }

    private void requireOwnedAlert(long userId, long alertId) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT t.user_id FROM sentinel_alert a JOIN sentinel_task t ON t.id=a.task_id WHERE a.id=?",
                alertId);
        if (rows.isEmpty() || ((Number) rows.get(0).get("user_id")).longValue() != userId) {
            throw new BusinessException(404, "告警不存在或无权限访问");
        }
    }

    private Map<String, Object> requireProfile(long userId, long profileId) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT id,task_id,metric,suggested_threshold,status FROM sentinel_learning_profile WHERE id=? AND user_id=?",
                profileId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "学习基线不存在");
        return camelize(rows.get(0));
    }

    private String templateRules(long templateId) {
        List<String> rules = jdbc.queryForList("SELECT rules_json FROM sentinel_threshold_template WHERE id=?",
                String.class, templateId);
        return rules.isEmpty() ? null : rules.get(0);
    }

    private List<Rule> readRules(String raw) {
        List<Rule> rules = new ArrayList<>();
        for (Map<String, Object> item : readRawRules(raw)) {
            String metric = str(item.get("metric"));
            double value = item.get("value") instanceof Number number ? number.doubleValue() : Double.NaN;
            if (metric.isBlank() || Double.isNaN(value)) continue;
            rules.add(new Rule(metric, str(item.getOrDefault("operator", "gt")), value));
        }
        return rules;
    }

    private List<Map<String, Object>> readRawRules(String raw) {
        if (raw == null || raw.isBlank()) return new ArrayList<>();
        try {
            return json.readValue(raw, new TypeReference<List<Map<String, Object>>>() {});
        } catch (com.fasterxml.jackson.core.JsonProcessingException failure) {
            return new ArrayList<>();
        }
    }

    private Stats stats(long taskId, String metric) {
        List<Double> values = jdbc.queryForList(
                "SELECT value_num FROM sentinel_metric_sample WHERE task_id=? AND metric=? AND value_num IS NOT NULL "
                        + "ORDER BY sampled_at DESC LIMIT " + BASELINE_WINDOW,
                Double.class, taskId, metric);
        if (values.isEmpty()) return new Stats(0, 0, 0, 0, 0, 0);
        List<Double> sorted = values.stream().sorted(Comparator.naturalOrder()).toList();
        double sum = sorted.stream().mapToDouble(Double::doubleValue).sum();
        return new Stats(sorted.size(), sum / sorted.size(), percentile(sorted, 0.95),
                percentile(sorted, 0.05), sorted.get(0), sorted.get(sorted.size() - 1));
    }

    private static double percentile(List<Double> sorted, double ratio) {
        int index = (int) Math.floor(ratio * (sorted.size() - 1));
        return sorted.get(Math.max(0, Math.min(index, sorted.size() - 1)));
    }

    private List<Map<String, Object>> evidenceOf(long alertId) {
        return jdbc.queryForList(
                        "SELECT id,kind,title,detail,created_at FROM sentinel_guardian_evidence WHERE alert_id=? ORDER BY id",
                        alertId)
                .stream().map(this::camelize).toList();
    }

    private Map<String, Object> camelize(Map<String, Object> row) {
        Map<String, Object> result = new LinkedHashMap<>();
        row.forEach((key, value) -> result.put(toCamel(key), value));
        return result;
    }

    private static String toCamel(String key) {
        String lower = key.toLowerCase(Locale.ROOT);
        StringBuilder builder = new StringBuilder();
        boolean upperNext = false;
        for (char character : lower.toCharArray()) {
            if (character == '_') {
                upperNext = true;
                continue;
            }
            builder.append(upperNext ? Character.toUpperCase(character) : character);
            upperNext = false;
        }
        return builder.toString();
    }

    private static String str(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private static String truncate(String value, int max) {
        if (value == null) return null;
        return value.length() <= max ? value : value.substring(0, max);
    }

    private record Rule(String metric, String operator, double value) {}

    private record Stats(int count, double avg, double p95, double p05, double min, double max) {}
}
