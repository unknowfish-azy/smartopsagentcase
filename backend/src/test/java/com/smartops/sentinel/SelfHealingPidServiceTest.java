package com.smartops.sentinel;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * SelfHealingPidService 单测。
 *
 * <p>PID 服务自行从 DB 查数值：
 * threshold → sentinel_learning_profile.suggested_threshold / current_threshold
 * observed  → sentinel_metric_sample.value_num WHERE abnormal=TRUE
 * 调用方只传 task_id + metric。</p>
 */
class SelfHealingPidServiceTest {

    private static final long TASK = 101L;
    private static final String METRIC = "cpu_usage";
    private static final double KP = 0.6;
    private static final double KI = 0.1;

    private JdbcTemplate jdbc;
    private SelfHealingPidService pid;

    @BeforeEach
    void setup() {
        jdbc = mock(JdbcTemplate.class);
        pid = new SelfHealingPidService(jdbc);
    }

    /** mock loadOrInit 返回空（首次告警）。 */
    @SuppressWarnings("unchecked")
    private void mockEmptyPidState() {
        when(jdbc.query(anyString(), any(RowMapper.class), anyLong(), anyString()))
                .thenReturn(List.of());
    }

    /** mock loadOrInit 返回指定 integral/execCount/lastExecutedAt。 */
    @SuppressWarnings("unchecked")
    private void mockPidState(double integral, Instant lastExec, int execCount) {
        when(jdbc.query(anyString(), any(RowMapper.class), eq(TASK), eq(METRIC)))
                .thenAnswer(invocation -> {
                    RowMapper<?> mapper = invocation.getArgument(1);
                    ResultSet rs = mock(ResultSet.class);
                    when(rs.getDouble("kp")).thenReturn(KP);
                    when(rs.getDouble("ki")).thenReturn(KI);
                    when(rs.getDouble("kd")).thenReturn(0.0);
                    when(rs.getDouble("integral")).thenReturn(integral);
                    when(rs.getDouble("last_error")).thenReturn(0.1);
                    when(rs.getDouble("last_intensity")).thenReturn(0.5);
                    when(rs.getTimestamp("last_executed_at")).thenReturn(
                            lastExec != null ? Timestamp.from(lastExec) : null);
                    when(rs.getInt("execution_count")).thenReturn(execCount);
                    when(rs.getBoolean("enabled")).thenReturn(true);
                    return List.of(mapper.mapRow(rs, 0));
                });
    }

    /** mock lookupThreshold → 返回指定 DOUBLE（匹配 learning_profile SQL）。 */
    private void mockThreshold(double threshold) {
        when(jdbc.queryForObject(containsString("learning_profile"), eq(Double.class), eq(TASK), eq(METRIC)))
                .thenReturn(threshold);
    }

    /** mock lookupLatestAbnormalSample → 返回指定 DOUBLE（匹配 metric_sample SQL）。 */
    private void mockAbnormalSample(double observed) {
        when(jdbc.queryForObject(containsString("metric_sample"), eq(Double.class), anyLong(), anyString()))
                .thenReturn(observed);
    }

    private static String containsString(String substring) {
        return org.mockito.ArgumentMatchers.contains(substring);
    }

    /* ── 降级：无 threshold → 默认 0.5 ──────────────────────────── */

    @Test
    @DisplayName("无 threshold 数值 → 默认 0.5，不做归一化")
    void noThreshold_default05() {
        when(jdbc.queryForObject(anyString(), eq(Double.class), eq(TASK), eq(METRIC)))
                .thenReturn(null);
        assertEquals(0.5, pid.calculateIntensity(TASK, METRIC), 0.001);
    }

    @Test
    @DisplayName("threshold=0 → 默认 0.5")
    void zeroThreshold_default05() {
        mockThreshold(0.0);
        assertEquals(0.5, pid.calculateIntensity(TASK, METRIC), 0.001);
    }

    @Test
    @DisplayName("无 abnormal sample → 默认 0.5")
    void noSample_default05() {
        mockThreshold(80.0);
        when(jdbc.queryForObject(anyString(), eq(Double.class), anyLong(), anyString()))
                .thenReturn(null);
        assertEquals(0.5, pid.calculateIntensity(TASK, METRIC), 0.001);
    }

    /* ── 首次告警（execution_count=0）→ 跳过 I ────────────────── */

    @Test
    @DisplayName("首次告警：observed 小 → P=0.6*0.0625=0.0375 → clamp lo=0.1")
    void firstAlert_smallObserved() {
        mockThreshold(80.0);
        mockAbnormalSample(85.0); // e=(85-80)/80=0.0625
        mockEmptyPidState();

        double intensity = pid.calculateIntensity(TASK, METRIC);
        assertEquals(0.1, intensity, 0.001, "首次 P 太小 → clamp lo=0.1");
    }

    @Test
    @DisplayName("首次告警大误差：e=1.0 → P=0.6 → intensity=0.6")
    void firstAlert_largeError() {
        mockThreshold(80.0);
        mockAbnormalSample(160.0); // e=1.0
        mockEmptyPidState();

        assertEquals(0.6, pid.calculateIntensity(TASK, METRIC), 0.001);
    }

    /* ── P+I 联合（execCount>0，非 tooFrequent）────────────────── */

    @Test
    @DisplayName("有历史 integral=0.5、execCount=3、1h 前 → P+I 叠加")
    void hasHistory_pPlusI() {
        mockThreshold(80.0);
        mockAbnormalSample(90.0); // e=0.125, P=0.075
        mockPidState(0.5, Instant.now().minusSeconds(3600), 3);

        // P=0.075, I=0.1*0.5=0.05 → 0.125（在 0.1~1.0 内不 clamp）
        assertEquals(0.125, pid.calculateIntensity(TASK, METRIC), 0.001);
    }

    @Test
    @DisplayName("大误差 P 主导：e=1.0, integral=0.8 → 0.68")
    void largeError_pDominates() {
        mockThreshold(80.0);
        mockAbnormalSample(160.0); // e=1.0, P=0.6
        mockPidState(0.8, Instant.now().minusSeconds(7200), 5);
        assertEquals(0.68, pid.calculateIntensity(TASK, METRIC), 0.001);
    }

    @Test
    @DisplayName("极大误差 clamp 到 1.0")
    void veryLargeError_clampHigh() {
        mockThreshold(80.0);
        mockAbnormalSample(1000.0); // e=11.5, P=6.9 → clamp hi=1.0
        mockPidState(0.0, null, 1);
        assertEquals(1.0, pid.calculateIntensity(TASK, METRIC), 0.001);
    }

    /* ── tooFrequent 跳过 I ─────────────────────────────────────── */

    @Test
    @DisplayName("5 分钟内再告警 → tooFrequent → 只用 P")
    void tooFrequent_skipsI() {
        mockThreshold(80.0);
        mockAbnormalSample(90.0); // e=0.125, P=0.075
        // lastExecutedAt = 5 分钟前（tooFrequent < 10min）
        mockPidState(0.5, Instant.now().minusSeconds(300), 2);

        // 只用 P：0.075 → clamp lo=0.1
        assertEquals(0.1, pid.calculateIntensity(TASK, METRIC), 0.001);
    }

    /* ── recordExecutionResult ────────────────────────────────────── */

    @Test
    @DisplayName("recordExecutionResult: 0.7*1.0+(-0.05)=0.65")
    void recordResult_integralDecay() {
        mockPidState(1.0, Instant.now().minusSeconds(3600), 3);
        pid.recordExecutionResult(TASK, METRIC, -0.05);
        verify(jdbc).update(anyString(), anyDouble(), eq(-0.05), any(Timestamp.class),
                eq(TASK), eq(METRIC));
    }

    @Test
    @DisplayName("integral clamp 边界")
    void integralClamp() {
        assertEquals(2.0, SelfHealingPidService.clamp(0.7 * 1.0 + 5.0, -2.0, 2.0), 0.001);
        assertEquals(-2.0, SelfHealingPidService.clamp(0.7 * -1.0 + -5.0, -2.0, 2.0), 0.001);
    }

    /* ── onAlertResolved ────────────────────────────────────────── */

    @Test
    @DisplayName("onResolved: 无 threshold → 跳过")
    void onResolved_noThreshold_skip() {
        when(jdbc.queryForObject(anyString(), eq(Double.class), eq(TASK), eq(METRIC)))
                .thenReturn(null);
        pid.onAlertResolved(TASK, METRIC, Instant.now());
        verify(jdbc, never()).update(anyString(), anyDouble(), anyDouble(), any(Timestamp.class),
                anyLong(), anyString());
    }

    @Test
    @DisplayName("onResolved: 无 post sample → 跳过反馈")
    void onResolved_noSample_skip() {
        mockThreshold(80.0);
        // resolved 后第一个 sample 返回 null
        when(jdbc.queryForObject(anyString(), eq(Double.class), anyLong(), anyString(), any(Timestamp.class)))
                .thenReturn(null);
        pid.onAlertResolved(TASK, METRIC, Instant.now());
        verify(jdbc, never()).update(anyString(), anyDouble(), anyDouble(), any(Timestamp.class),
                anyLong(), anyString());
    }

    @Test
    @DisplayName("onResolved: 有 post sample → integral 更新")
    void onResolved_hasSample() {
        mockThreshold(80.0);
        // resolved 后第一个 sample = 75（收敛到阈值以下）
        when(jdbc.queryForObject(anyString(), eq(Double.class), anyLong(), anyString(), any(Timestamp.class)))
                .thenReturn(75.0);
        // recordExecutionResult 需要 loadOrInit
        mockPidState(0.5, Instant.now().minusSeconds(3600), 3);

        pid.onAlertResolved(TASK, METRIC, Instant.now());

        // errorAfter = (75-80)/80 = -0.0625
        // newIntegral = 0.7*0.5 + (-0.0625) = 0.2875
        verify(jdbc).update(anyString(), anyDouble(), eq(-0.0625), any(Timestamp.class),
                eq(TASK), eq(METRIC));
    }

    /* ── utility ─────────────────────────────────────────────────── */

    @Test
    @DisplayName("clamp / round2")
    void utilities() {
        assertEquals(0.5, SelfHealingPidService.clamp(0.5, 0.1, 1.0), 0.001);
        assertEquals(0.1, SelfHealingPidService.clamp(-0.5, 0.1, 1.0), 0.001);
        assertEquals(1.0, SelfHealingPidService.clamp(2.5, 0.1, 1.0), 0.001);
        assertEquals(0.12, SelfHealingPidService.round2(0.12345), 0.001);
        assertEquals(1.0, SelfHealingPidService.round2(0.999), 0.001);
    }
}
