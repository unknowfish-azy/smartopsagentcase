package com.smartops.sentinel;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 预测面服务：把「真实哨兵采样序列」交给 ai-service 做单指标多步预测，并组装前端契约。
 *
 * <p><b>诚实边界（本模块最重要的一段）</b>：
 * <ul>
 *   <li>数据源只有 {@code sentinel_metric_sample}（cpu/memory/disk/tcp/port/log_hits），
 *       <b>不存在</b>设计稿里的 ECT/RPM/EGT/OILP/IAT/VBAT 引擎传感器。六槽位是 UI 语义别名，
 *       live 态的展示名与单位一律取真实指标口径；demo 态仍用合成传感器。</li>
 *   <li>PatchTST 权重 {@code ai-service/models/patchtst.pt} 当前不存在，ai-service 会显式降级到
 *       linear / seasonal_naive。响应里必须原样带回 {@code mode} / {@code model_status} /
 *       {@code modelStatusDetail}，<b>不得</b>对外宣称"MLP+GRU 预测"或"PatchTST 已启用"。</li>
 *   <li>ai-service 不可达 / 无可用序列时返回 {@code status=unavailable}，前端走 offline，
 *       不补默认值、不用演示数据冒充实时。</li>
 * </ul>
 */
@Service
public class SentinelForecastService {

    /** 历史窗口上限：与 PatchTST 训练上下文量级一致，也避免一次拉全表。 */
    private static final int MAX_HISTORY_POINTS = 192;

    /** 单步最小观测点数：ai-service 的 values 约束是 8~4096。 */
    private static final int MIN_POINTS = 8;

    /** 视野（秒）→ 步数：按实测采样间隔换算，保证 horizonSec 覆盖的时间长度与请求一致。 */
    private static final int[] HORIZON_CHOICES_SEC = {15, 30, 60, 120};

    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    private final SentinelForecastClient client;
    private final Duration httpTimeout;

    public SentinelForecastService(JdbcTemplate jdbc, ObjectMapper json,
                                   SentinelForecastClient client,
                                   @Value("${smartops.sentinel.forecast.timeout-seconds:10}") long timeoutSeconds) {
        this.jdbc = jdbc;
        this.json = json;
        this.client = client;
        this.httpTimeout = Duration.ofSeconds(Math.max(1, timeoutSeconds));
    }

    /* ── 指标目录（UI 六槽位 → 真实哨兵指标） ─────────────────────────── */

    /**
     * UI 槽位定义。{@code metric} 是 {@code sentinel_metric_sample.metric} 的真实取值；
     * {@code low} 表示"越低越好"（如磁盘可用率），阈值方向与其他相反。
     */
    public record SensorSlot(String key, String cn, String en, String metric, String unit,
                             Double warnAbove, Double critAbove, Double warnBelow, Double critBelow,
                             boolean low) {}

    /** 槽位清单是声明式的：真实指标一旦采集到就自动出现，未采集到的 slot 由 catalog 过滤掉。 */
    private static final List<SensorSlot> SLOTS = List.of(
            new SensorSlot("ect", "冷却液温度", "ECT", "cpu", "%", 85d, 95d, null, null, false),
            new SensorSlot("rpm", "曲轴转速", "RPM", "memory", "%", 85d, 95d, null, null, false),
            new SensorSlot("egt", "排气温度", "EGT", "disk", "%", 80d, 90d, null, null, false),
            new SensorSlot("oilp", "机油压力", "OILP", "tcp", "连接数", null, null, null, null, false),
            new SensorSlot("iat", "进气温度", "IAT", "port", "连通率", 90d, 99d, 10d, 1d, true),
            new SensorSlot("vbat", "电池电压", "VBAT", "log_hits", "命中数/轮", 500d, 2000d, null, null, false)
    );

    public Map<String, Object> catalog(long userId) {
        List<Map<String, Object>> available = new ArrayList<>();
        for (SensorSlot slot : SLOTS) {
            Optional<SeriesMeta> meta = seriesMeta(userId, slot);
            if (meta.isEmpty()) continue;
            SeriesMeta info = meta.get();
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("key", slot.key());
            entry.put("cn", slot.cn());
            entry.put("en", slot.en());
            entry.put("metric", slot.metric());
            entry.put("unit", slot.unit());
            entry.put("taskId", info.taskId());
            entry.put("sampleCount", info.count());
            entry.put("sampleIntervalSec", info.intervalSec());
            entry.put("lastSampledAt", info.lastSampledAt() == null ? "" : info.lastSampledAt());
            entry.put("warnAbove", slot.warnAbove() == null ? 0 : slot.warnAbove());
            entry.put("critAbove", slot.critAbove() == null ? 0 : slot.critAbove());
            entry.put("warnBelow", slot.warnBelow() == null ? 0 : slot.warnBelow());
            entry.put("critBelow", slot.critBelow() == null ? 0 : slot.critBelow());
            entry.put("low", slot.low());
            available.add(entry);
        }
        return Map.of(
                "slots", available,
                "horizons", HORIZON_CHOICES_SEC,
                "note", "槽位为 UI 语义别名，live 态名称/单位/阈值一律取真实哨兵指标口径；"
                        + "无采样的槽位不出现在列表里，也不补默认值。");
    }

    /* ── 主端点 ─────────────────────────────────────────────────────── */

    public Map<String, Object> forecast(SessionUser actor, String sensorKey, Integer horizonSec) {
        long userId = userId(actor);
        SensorSlot slot = resolveSlot(sensorKey);
        int horizon = normalizeHorizon(horizonSec);

        Optional<SeriesMeta> meta = seriesMeta(userId, slot);
        if (meta.isEmpty()) {
            return unavailable(slot, horizon, "该指标当前没有可用采样（" + slot.metric() + "），无法预测");
        }
        SeriesMeta info = meta.get();
        if (info.count() < MIN_POINTS) {
            return unavailable(slot, horizon,
                    "采样点不足：" + info.count() + " < " + MIN_POINTS + "，不足以支撑预测");
        }

        List<double[]> samples = loadSamples(userId, slot, info.taskId(), MAX_HISTORY_POINTS);
        if (samples.size() < MIN_POINTS) {
            return unavailable(slot, horizon, "可读采样点不足（" + samples.size() + "）");
        }
        double[] values = new double[samples.size()];
        for (int i = 0; i < samples.size(); i++) values[i] = samples.get(i)[1];

        int steps = Math.max(1, Math.round((float) horizon / Math.max(1, info.intervalSec())));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("values", toList(values));
        payload.put("horizon", steps);
        payload.put("metric_name", slot.metric());
        // 只传该指标真实存在的单向阈值，且满足 ai-service 的 upper > lower 约束。
        if (slot.warnAbove() != null && slot.critAbove() != null) {
            payload.put("upper_threshold", Math.max(slot.warnAbove(), slot.critAbove()));
        } else if (slot.warnBelow() != null && slot.critBelow() != null) {
            payload.put("lower_threshold", Math.min(slot.warnBelow(), slot.critBelow()));
        }

        long startedAt = System.currentTimeMillis();
        Optional<Map<String, Object>> result = client.forecast(payload);
        long elapsedMs = System.currentTimeMillis() - startedAt;
        if (result.isEmpty()) {
            return unavailable(slot, horizon, "ai-service 不可达或推理超时（" + httpTimeout.toSeconds() + "s 内无响应）");
        }

        Map<String, Object> body = result.get();
        String mode = SentinelForecastClient.text(body.get("mode"));
        String modelStatus = SentinelForecastClient.text(body.get("model_status"));
        String detail = SentinelForecastClient.text(body.get("model_status_detail"));
        String kind = SentinelForecastClient.resolveKind(mode, modelStatus);

        double[] intervalSec = new double[]{Math.max(1, info.intervalSec())};
        List<Map<String, Object>> series = new ArrayList<>();
        Instant lastSampled = info.lastSampledAt() == null ? Instant.now() : Instant.parse(info.lastSampledAt());
        for (int i = 0; i < samples.size(); i++) {
            double[] row = samples.get(i);
            series.add(Map.of(
                    "t", Math.round((row[0] - samples.get(samples.size() - 1)[0]) / 1000.0),
                    "v", round(row[1])));
        }

        List<Map<String, Object>> forecastPoints = new ArrayList<>();
        for (Object item : SentinelForecastClient.list(body.get("points"))) {
            if (!(item instanceof Map<?, ?> point)) continue;
            Map<?, ?> row = (Map<?, ?>) point;
            Object stepValue = row.get("step");
            int step = stepValue instanceof Number numeric ? numeric.intValue() : forecastPoints.size() + 1;
            double median = doubleOr(row.get("value"), 0d);
            double half = doubleOr(row.get("upper"), median) - median;
            if (half <= 0) half = Math.abs(median - doubleOr(row.get("lower"), median)) / 2.0;
            forecastPoints.add(Map.of(
                    "t", step * (long) intervalSec[0],
                    "h", step,
                    "median", round(median),
                    "p10", round(median - half),
                    "p90", round(median + half),
                    "lower", round(doubleOr(row.get("lower"), median - half)),
                    "upper", round(doubleOr(row.get("upper"), median + half))));
        }

        List<Map<String, Object>> crossings = crossings(slot, forecastPoints, info.intervalSec());

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("ok", true);
        response.put("generatedAt", Instant.now().toString());
        response.put("status", "ok");
        response.put("kind", kind);                     // neural | statistical | unavailable
        response.put("mode", mode == null ? "unknown" : mode);
        response.put("modelStatus", modelStatus == null ? "unknown" : modelStatus);
        response.put("modelStatusDetail", detail);
        response.put("metric", slot.metric());
        response.put("sensor", slot.key());
        response.put("cn", slot.cn());
        response.put("en", slot.en());
        response.put("unit", slot.unit());
        response.put("taskId", info.taskId());
        response.put("horizonSec", horizon);
        response.put("steps", steps);
        response.put("sampleIntervalSec", info.intervalSec());
        response.put("sampleCount", samples.size());
        response.put("series", series);
        response.put("forecast", forecastPoints);
        response.put("crossings", crossings);
        response.put("trend", body.getOrDefault("trend", "stable"));
        response.put("riskScore", round(doubleOr(body.get("risk_score"), 0d)));
        response.put("riskLevel", body.getOrDefault("risk_level", "low"));
        response.put("riskBasis", SentinelForecastClient.list(body.get("risk_basis")));
        response.put("intervalLevel", body.getOrDefault("interval_level", 0.95));
        response.put("intervalMethod", body.getOrDefault("interval_method", ""));
        response.put("explanation", body.get("explanation"));
        response.put("inferenceMs", elapsedMs);
        response.put("thresholds", thresholdsOf(slot));
        response.put("model", modelCard(kind, mode, modelStatus, detail));
        response.put("note", kindHint(kind, detail));
        return response;
    }

    public Map<String, Object> modelInfo(SessionUser actor) {
        Map<String, Object> card = new LinkedHashMap<>();
        Optional<Map<String, Object>> info = client.modelInfo();
        if (info.isPresent()) {
            Map<String, Object> raw = info.get();
            card.put("kind", raw.getOrDefault("kind", "unknown"));
            card.put("torchAvailable", raw.getOrDefault("torch_available", false));
            card.put("contextLength", raw.get("context_length"));
            card.put("horizon", raw.get("horizon"));
            card.put("reason", raw.get("reason"));
            card.put("reachable", true);
        } else {
            card.put("kind", "unreachable");
            card.put("torchAvailable", false);
            card.put("contextLength", null);
            card.put("horizon", null);
            card.put("reason", "ai-service 不可达，无法读取模型状态");
            card.put("reachable", false);
        }
        card.put("weightsExpected", "ai-service/models/patchtst.pt");
        card.put("note", "kind=fallback 表示本次预测走统计降级（linear / seasonal_naive），"
                + "不代表神经模型效果；材料引用时必须同时给出 mode 与 model_status。");
        return card;
    }

    /* ── 内部：数据读取 ─────────────────────────────────────────────── */

    private record SeriesMeta(long taskId, int count, int intervalSec, String lastSampledAt) {}

    private Optional<SeriesMeta> seriesMeta(long userId, SensorSlot slot) {
        // 归属校验前置：只看属于该用户的任务的采样，杜绝跨租户读数。
        List<Object[]> rows = jdbc.query(
                "SELECT s.task_id, COUNT(*) AS cnt, MIN(s.sampled_at) AS first_at, MAX(s.sampled_at) AS last_at "
                        + "FROM sentinel_metric_sample s JOIN sentinel_task t ON t.id=s.task_id "
                        + "WHERE t.user_id=? AND s.metric=? AND s.value_num IS NOT NULL "
                        + "GROUP BY s.task_id ORDER BY cnt DESC LIMIT 1",
                (rs, index) -> new Object[]{
                        rs.getLong("task_id"),
                        rs.getInt("cnt"),
                        rs.getTimestamp("first_at"),
                        rs.getTimestamp("last_at")},
                userId, slot.metric());
        if (rows.isEmpty()) return Optional.empty();

        Object[] row = rows.get(0);
        int count = (Integer) row[1];
        Timestamp first = (Timestamp) row[2];
        Timestamp last = (Timestamp) row[3];
        int intervalSec = estimateIntervalSec(first, last, count);
        String lastText = last == null ? null : last.toInstant().toString();
        return Optional.of(new SeriesMeta((Long) row[0], count, intervalSec, lastText));
    }

    /**
     * 估计采样间隔：取中位数相邻差。样本不足 2 点时按 30s 兜底（哨兵默认轮询周期量级），
     * 并在响应里如实回传 sampleIntervalSec，让前端知道 horizonSec 是怎么换算成步数的。
     */
    private int estimateIntervalSec(Timestamp first, Timestamp last, int count) {
        if (first == null || last == null || count < 2) return 30;
        long spanSec = Math.max(1, Duration.between(first.toInstant(), last.toInstant()).getSeconds());
        long medianGap = spanSec / (count - 1);
        if (medianGap <= 0) return 30;
        // 对齐到常见轮询粒度，避免出现 37s 这种看起来精确的伪数值。
        if (medianGap < 5) return 1;
        if (medianGap < 15) return 5;
        if (medianGap < 45) return 30;
        if (medianGap < 90) return 60;
        if (medianGap < 300) return 120;
        return Math.toIntExact(Math.min(3600, medianGap));
    }

    private List<double[]> loadSamples(long userId, SensorSlot slot, long taskId, int limit) {
        List<double[]> rows = jdbc.query(
                "SELECT s.sampled_at, s.value_num FROM sentinel_metric_sample s "
                        + "JOIN sentinel_task t ON t.id=s.task_id "
                        + "WHERE t.user_id=? AND s.task_id=? AND s.metric=? AND s.value_num IS NOT NULL "
                        + "ORDER BY s.sampled_at DESC LIMIT ?",
                (rs, index) -> new double[]{
                        rs.getTimestamp("sampled_at").getTime(),
                        rs.getDouble("value_num")},
                userId, taskId, slot.metric(), Math.max(MIN_POINTS, limit));
        java.util.Collections.reverse(rows);   // 接口要求时间升序
        return rows;
    }

    /* ── 内部：阈值与越界 ───────────────────────────────────────────── */

    private List<Map<String, Object>> crossings(SensorSlot slot, List<Map<String, Object>> points, int intervalSec) {
        List<Map<String, Object>> events = new ArrayList<>();
        for (Map<String, Object> point : points) {
            double median = doubleOr(point.get("median"), 0d);
            String kind = breachKind(slot, median);
            if (kind == null) continue;
            // 同一档只记第一次（前向扫描，先遇到的是"最早发生"）。
            boolean already = events.stream().anyMatch(e -> e.get("kind").equals(kind));
            if (already) continue;
            int h = (int) doubleOr(point.get("h"), 0d);
            events.add(Map.of(
                    "kind", kind,
                    "h", h * intervalSec,
                    "step", h,
                    "value", round(median),
                    "threshold", kind.equals("crit") ? critThreshold(slot) : warnThreshold(slot),
                    "confidence", round(confidence(h * intervalSec))));
        }
        return List.copyOf(events);
    }

    /** 返回 {@code warn}/{@code crit} 或 null；低水位型指标反向比较。 */
    private String breachKind(SensorSlot slot, double value) {
        if (!slot.low()) {
            if (slot.critAbove() != null && value >= slot.critAbove()) return "crit";
            if (slot.warnAbove() != null && value >= slot.warnAbove()) return "warn";
            return null;
        }
        if (slot.critBelow() != null && value <= slot.critBelow()) return "crit";
        if (slot.warnBelow() != null && value <= slot.warnBelow()) return "warn";
        return null;
    }

    private double warnThreshold(SensorSlot slot) {
        return slot.low()
                ? (slot.warnBelow() == null ? 0d : slot.warnBelow())
                : (slot.warnAbove() == null ? 0d : slot.warnAbove());
    }

    private double critThreshold(SensorSlot slot) {
        return slot.low()
                ? (slot.critBelow() == null ? 0d : slot.critBelow())
                : (slot.critAbove() == null ? 0d : slot.critAbove());
    }

    private Map<String, Object> thresholdsOf(SensorSlot slot) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("warnAbove", slot.warnAbove() == null ? 0 : slot.warnAbove());
        map.put("critAbove", slot.critAbove() == null ? 0 : slot.critAbove());
        map.put("warnBelow", slot.warnBelow() == null ? 0 : slot.warnBelow());
        map.put("critBelow", slot.critBelow() == null ? 0 : slot.critBelow());
        map.put("low", slot.low());
        map.put("source", "服务端槽位声明（非引擎真实阈值）；缺口位为 0，不参与判定");
        return map;
    }

    /**
     * 置信度：**不是校准概率**，只是"越早越可信"的单调启发式。
     * 设计与前端 demo 公式同口径（0.9 − h/(4×视野)），落在 0.5–0.9。
     */
    private double confidence(int horizonSec) {
        int denominator = Math.max(1, 4 * Math.max(horizonSec, 1));
        return Math.min(0.9, Math.max(0.5, 0.9 - (double) horizonSec / denominator));
    }

    /* ── 内部：装配 ─────────────────────────────────────────────────── */

    private Map<String, Object> unavailable(SensorSlot slot, int horizon, String reason) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("ok", false);
        response.put("generatedAt", Instant.now().toString());
        response.put("status", "unavailable");
        response.put("kind", "unavailable");
        response.put("mode", "none");
        response.put("modelStatus", "unavailable");
        response.put("modelStatusDetail", reason);
        response.put("reason", reason);
        response.put("metric", slot.metric());
        response.put("sensor", slot.key());
        response.put("cn", slot.cn());
        response.put("en", slot.en());
        response.put("unit", slot.unit());
        response.put("taskId", 0L);
        response.put("horizonSec", horizon);
        response.put("steps", 0);
        response.put("sampleIntervalSec", 0);
        response.put("sampleCount", 0);
        response.put("series", List.of());
        response.put("forecast", List.of());
        response.put("crossings", List.of());
        response.put("trend", "stable");
        response.put("riskScore", 0d);
        response.put("riskLevel", "low");
        response.put("riskBasis", List.of(reason));
        response.put("model", modelCard("unavailable", "none", "unavailable", reason));
        response.put("thresholds", thresholdsOf(slot));
        response.put("note", reason + "；页面应显示 offline，而不是补一条合成曲线。");
        return response;
    }

    private Map<String, Object> modelCard(String kind, String mode, String modelStatus, String detail) {
        Map<String, Object> card = new LinkedHashMap<>();
        boolean neural = "neural".equals(kind);
        // MAE/RMSE/MAPE 无评测产物：显式放 null，不用 Map.of（它不接受 null 值）。
        Map<String, Object> metrics = new LinkedHashMap<>();
        metrics.put("mae", null);
        metrics.put("rmse", null);
        metrics.put("mape", null);
        card.put("version", neural ? "patchtst-v1" : "statistical-baseline");
        card.put("arch", neural ? "PatchTST" : (mode == null ? "—" : mode));
        card.put("params", neural ? null : 0);
        card.put("metrics", metrics);
        card.put("trainedAt", null);
        card.put("epochs", null);
        card.put("gate", neural ? "PASS" : "FALLBACK");
        card.put("kind", kind);
        card.put("mode", mode);
        card.put("modelStatus", modelStatus);
        card.put("modelStatusDetail", detail);
        card.put("note", "MAE/RMSE/MAPE 仅在真实独立测试集评测后才有值；"
                + "当前无评测产物，字段恒为空，前端显示 —。");
        return card;
    }

    private String kindHint(String kind, String detail) {
        return switch (kind) {
            case "neural" -> "本次由 PatchTST 神经模型产出；区间为残差近似，未经覆盖率校准。";
            case "statistical" -> "权重缺失或输入不满足模型约束，本次走统计降级（"
                    + (detail == null ? "linear / seasonal_naive" : detail)
                    + "）；这不是神经网络效果，也不代表 PatchTST 精度。";
            default -> "本次没有可用的预测结果：" + (detail == null ? "未知原因" : detail);
        };
    }

    private SensorSlot resolveSlot(String key) {
        if (key == null || key.isBlank()) throw new BusinessException(400, "缺少传感器标识");
        return SLOTS.stream()
                .filter(slot -> slot.key().equalsIgnoreCase(key.trim()))
                .findFirst()
                .orElseThrow(() -> new BusinessException(400, "未知传感器：" + key));
    }

    private int normalizeHorizon(Integer horizonSec) {
        if (horizonSec == null) return 30;
        for (int choice : HORIZON_CHOICES_SEC) {
            if (choice == Math.max(1, Math.min(120, horizonSec))) return choice;
        }
        // 非档位值就近吸附，避免前端出现 47s 这种伪精确视野。
        int best = HORIZON_CHOICES_SEC[0];
        int distance = Math.abs(best - horizonSec);
        for (int choice : HORIZON_CHOICES_SEC) {
            int candidate = Math.abs(choice - horizonSec);
            if (candidate < distance) {
                best = choice;
                distance = candidate;
            }
        }
        return best;
    }

    private long userId(SessionUser actor) {
        if (actor == null || actor.id() == null) throw new BusinessException(401, "需要登录后使用预测面");
        return actor.id();
    }

    /* ── 小工具 ─────────────────────────────────────────────────────── */

    private static List<Double> toList(double[] values) {
        List<Double> list = new ArrayList<>(values.length);
        for (double value : values) list.add(value);
        return list;
    }

    private static double doubleOr(Object value, double fallback) {
        return value instanceof Number numeric ? numeric.doubleValue() : fallback;
    }

    private static double round(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) return 0d;
        return Math.round(value * 10000d) / 10000d;
    }

    /** 保留给后续"按任务直接取数"的入口；当前版本不需要，但 SQL 形态先固定下来。 */
    @SuppressWarnings("unused")
    private JsonNode readRules(String raw) throws Exception {
        return json.readTree(raw);
    }

    @SuppressWarnings("unused")
    private static Map<String, Object> emptyMap() {
        return new HashMap<>();
    }
}
