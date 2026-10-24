package com.smartops.sentinel;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 阈值判定与防抖的内核测试。
 *
 * <p>这批用例与前端 {@code frontend/test/sentinel-model.test.mjs} 刻意重叠：
 * 两侧都实现了同一套语义，就必须用同一批断言钉住，避免一侧改了另一侧没跟上。</p>
 */
class SentinelThresholdTest {

    private static final List<SentinelThreshold.Rule> MEMORY_90 =
            List.of(new SentinelThreshold.Rule("memory", "gt", 90));

    @Test
    @DisplayName("单指标阈值只在运算符满足时命中，且 gt 是严格比较")
    void singleMetricThreshold() {
        assertTrue(SentinelThreshold.breached(MEMORY_90, Map.of("memory", 95.0)));
        assertFalse(SentinelThreshold.breached(MEMORY_90, Map.of("memory", 90.0)));
        assertFalse(SentinelThreshold.breached(MEMORY_90, Map.of("memory", 89.9)));
        assertTrue(SentinelThreshold.breached(List.of(new SentinelThreshold.Rule("memory", "gte", 90)), Map.of("memory", 90.0)));
    }

    @Test
    @DisplayName("复合阈值要求同一组规则全部满足")
    void compoundThreshold() {
        List<SentinelThreshold.Rule> rules = List.of(
                new SentinelThreshold.Rule("cpu", "gt", 85),
                new SentinelThreshold.Rule("memory", "gt", 80));
        assertTrue(SentinelThreshold.breached(rules, Map.of("cpu", 90.0, "memory", 85.0)));
        assertFalse(SentinelThreshold.breached(rules, Map.of("cpu", 90.0, "memory", 70.0)));
        assertFalse(SentinelThreshold.breached(rules, Map.of("cpu", 10.0, "memory", 99.0)));
    }

    @Test
    @DisplayName("指标缺失或非数字一律不命中：没有数据和指标异常是两件事")
    void missingObservationNeverFires() {
        assertFalse(SentinelThreshold.breached(MEMORY_90, Map.of()));
        assertFalse(SentinelThreshold.breached(MEMORY_90, Map.of("memory", Double.NaN)));
        assertFalse(SentinelThreshold.breached(MEMORY_90, Map.of("memory", Double.POSITIVE_INFINITY)));
        assertFalse(SentinelThreshold.breached(MEMORY_90, null));
        assertFalse(SentinelThreshold.breached(List.of(), Map.of("memory", 99.0)));
    }

    @Test
    @DisplayName("防抖：瞬时峰值不告警，必须连续满足到防抖时长才允许触发")
    void debounceSuppressesSpikes() {
        long start = 1_000_000L;
        SentinelThreshold.Decision justBreached = SentinelThreshold.debounce(
                MEMORY_90, Map.of("memory", 95.0), 300, null, start);
        assertEquals(new SentinelThreshold.Decision(true, false, 0, 300), justBreached);

        SentinelThreshold.Decision holding = SentinelThreshold.debounce(
                MEMORY_90, Map.of("memory", 95.0), 300, start, start + 299_000);
        assertFalse(holding.shouldFire());
        assertEquals(1, holding.remainingSec());

        SentinelThreshold.Decision fired = SentinelThreshold.debounce(
                MEMORY_90, Map.of("memory", 95.0), 300, start, start + 300_000);
        assertTrue(fired.shouldFire());
        assertEquals(0, fired.remainingSec());
    }

    @Test
    @DisplayName("指标恢复后不再告警，即使之前已经持续很久")
    void recoveryResets() {
        SentinelThreshold.Decision recovered = SentinelThreshold.debounce(
                MEMORY_90, Map.of("memory", 40.0), 300, 1_000_000L, 1_600_000L);
        assertFalse(recovered.breached());
        assertFalse(recovered.shouldFire());
        assertEquals(0, recovered.heldSec());
    }

    @Test
    @DisplayName("规则描述可读，且未配置时不谎称有阈值")
    void describesRules() {
        assertEquals("memory > 90", SentinelThreshold.describe(MEMORY_90));
        assertEquals("cpu > 85 且 disk ≥ 80", SentinelThreshold.describe(List.of(
                new SentinelThreshold.Rule("cpu", "gt", 85),
                new SentinelThreshold.Rule("disk", "gte", 80))));
        assertEquals("未配置阈值", SentinelThreshold.describe(List.of()));
    }

    @Test
    @DisplayName("未知运算符不命中，不会退化成默认放行")
    void unknownOperatorDoesNotFire() {
        assertFalse(SentinelThreshold.compare("matches", 95, 90));
        assertFalse(SentinelThreshold.breached(
                List.of(new SentinelThreshold.Rule("memory", "matches", 90)), Map.of("memory", 95.0)));
    }
}
