package com.smartops.sentinel;

import java.util.List;
import java.util.Map;

/**
 * 哨兵阈值判定内核。
 *
 * <p>与前端 {@code frontend/src/views/sentinel/sentinelModel.js} 的
 * {@code rulesBreached} / {@code debounceDecision} 保持**同一条语义**：
 * 复合阈值是"数组内全部满足"，持续时间防抖是"连续满足达到 debounceSec 才准触发"。
 * 两侧各有一份实现是有意为之：前端要即时反馈，后端才是判定权威。
 * 因此两侧都有针对同一批用例的测试，避免语义漂移。</p>
 */
public final class SentinelThreshold {

    private SentinelThreshold() {}

    /** 一条阈值规则；{@code metric} 为指标名，{@code operator} 取 gt/gte/lt/lte/ne/eq。 */
    public record Rule(String metric, String operator, double value) {
        public Rule {
            if (metric == null || metric.isBlank()) throw new IllegalArgumentException("规则缺少指标名");
            if (operator == null || operator.isBlank()) operator = "gt";
        }
    }

    /** 判定结果。{@code breached} 表示此刻是否越界，{@code shouldFire} 表示是否允许告警。 */
    public record Decision(boolean breached, boolean shouldFire, long heldSec, long remainingSec) {}

    public static boolean compare(String operator, double value, double threshold) {
        return switch (operator == null ? "gt" : operator) {
            case "gt" -> value > threshold;
            case "gte" -> value >= threshold;
            case "lt" -> value < threshold;
            case "lte" -> value <= threshold;
            case "ne" -> value != threshold;
            case "eq" -> value == threshold;
            default -> false;
        };
    }

    /**
     * 一组规则是否全部命中。
     *
     * <p>指标缺失、不是数字、或者 {@code NaN} 一律视为"不命中"，绝不因为读不到数据就告警 ——
     * "没有数据"和"指标异常"是两件完全不同的事。</p>
     */
    public static boolean breached(List<Rule> rules, Map<String, Double> snapshot) {
        if (rules == null || rules.isEmpty() || snapshot == null) return false;
        for (Rule rule : rules) {
            Double observed = snapshot.get(rule.metric());
            if (observed == null || observed.isNaN() || observed.isInfinite()) return false;
            if (!compare(rule.operator(), observed, rule.value())) return false;
        }
        return true;
    }

    /**
     * 持续时间防抖。
     *
     * @param breachedSinceMillis 该指标**连续**越界的起始时刻；null 表示此刻刚刚越界。
     *                            该状态必须由服务端持久化，不能只放在浏览器内存里，
     *                            否则刷新页面就会丢掉"已经持续了多久"。
     */
    public static Decision debounce(List<Rule> rules, Map<String, Double> snapshot, long debounceSec,
                                    Long breachedSinceMillis, long nowMillis) {
        if (!breached(rules, snapshot)) return new Decision(false, false, 0, 0);
        if (breachedSinceMillis == null) return new Decision(true, false, 0, Math.max(0, debounceSec));
        long heldSec = Math.max(0, (nowMillis - breachedSinceMillis) / 1000);
        long remainingSec = Math.max(0, debounceSec - heldSec);
        return new Decision(true, remainingSec == 0, heldSec, remainingSec);
    }

    /** 把规则渲染成人类可读的一段话，用于告警标题与界面展示。 */
    public static String describe(List<Rule> rules) {
        if (rules == null || rules.isEmpty()) return "未配置阈值";
        StringBuilder text = new StringBuilder();
        for (Rule rule : rules) {
            if (text.length() > 0) text.append(" 且 ");
            text.append(rule.metric()).append(' ').append(symbol(rule.operator())).append(' ').append(trim(rule.value()));
        }
        return text.toString();
    }

    private static String symbol(String operator) {
        return switch (operator == null ? "gt" : operator) {
            case "gt" -> ">";
            case "gte" -> "≥";
            case "lt" -> "<";
            case "lte" -> "≤";
            case "ne" -> "≠";
            case "eq" -> "=";
            default -> ">";
        };
    }

    private static String trim(double value) {
        return value == Math.rint(value) ? Long.toString((long) value) : Double.toString(value);
    }
}
