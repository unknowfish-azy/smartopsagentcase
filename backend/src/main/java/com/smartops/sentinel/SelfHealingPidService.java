package com.smartops.sentinel;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;

/**
 * 自愈闭环调参（PID 控制器）。
 *
 * <p>借鉴机器人 PID 闭环控制思想，解决哨兵处置"单发振荡"问题：
 * 处置脚本执行后指标变化没人看，下次告警还是同样强度处置，容易陷入
 * "猛冲→过冲→回调→再猛冲"的振荡。</p>
 *
 * <h3>数据来源</h3>
 * <ul>
 *   <li><b>threshold 数值</b>：从 {@code sentinel_learning_profile.suggested_threshold} 取
 *       （学习脚本已计算好的 DOUBLE 阈值），fallback 到 {@code current_threshold}；
 *       两者都没有 → 归一化跳过，用绝对变化率。</li>
 *   <li><b>observed 数值</b>：从 {@code sentinel_metric_sample.value_num} 取
 *       （Python 建模脚本写的 DOUBLE 采样值），不是 {@code sentinel_alert.observed_value}
 *       那个字符串描述列。</li>
 * </ul>
 *
 * <h3>PID 回路</h3>
 * <pre>
 *   告警触发 → calculateIntensity(taskId, metric)
 *           → 读最新 abnormal sample 做 observed
 *           → 读 learning_profile.suggested_threshold 做 threshold
 *           → e = (observed - threshold) / |threshold|
 *           → P = Kp × e, I = Ki × integral（首次或 tooFrequent 时 I=0）
 *           → intensity = clamp(P + I, 0.1, 1.0)
 *
 *   告警 resolved → onAlertResolved(taskId, metric, resolvedAt)
 *           → 读 resolved 后第一个 sample 做 resolvedValue
 *           → errorAfter = (resolvedValue - threshold) / |threshold|
 *           → integral = decay × integral + errorAfter（clamp ±integralClamp）
 * </pre>
 *
 * <h3>降级保护</h3>
 * <ul>
 *   <li>无 threshold 数值 → 默认强度 0.5；</li>
 *   <li>无 observed 或 resolved sample → 跳过；</li>
 *   <li>同一指标 tooFrequent（< minIntervalMin 分钟）→ 跳过 I 防振荡；</li>
 *   <li>PID 全局关闭 → 所有调用返回默认 0.5。</li>
 * </ul>
 */
@Slf4j
@Service
public class SelfHealingPidService {

    private final JdbcTemplate jdbc;

    @Value("${smartops.sentinel.healing.pid.enabled:true}")
    private boolean enabled = true;

    @Value("${smartops.sentinel.healing.pid.kp:0.6}")
    private double kp = 0.6;

    @Value("${smartops.sentinel.healing.pid.ki:0.1}")
    private double ki = 0.1;

    /** 积分项历史衰减系数（0.7 = 每次保留 70% 历史，30% 留给新值）。 */
    @Value("${smartops.sentinel.healing.pid.decay:0.7}")
    private double decay = 0.7;

    /** 同一指标两次 PID 调节的最小间隔（分钟），防高频振荡。 */
    @Value("${smartops.sentinel.healing.pid.min-interval-min:10}")
    private int minIntervalMin = 10;

    /** 积分项上限，防止饱和。 */
    @Value("${smartops.sentinel.healing.pid.integral-clamp:2.0}")
    private double integralClamp = 2.0;

    /** 默认强度（降级使用）。 */
    private static final double DEFAULT_INTENSITY = 0.5;

    public SelfHealingPidService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * 计算当前告警的处置强度（0.1 ~ 1.0）。
     *
     * @param taskId 哨兵任务 ID
     * @param metric 指标名（如 "cpu_usage"）
     * @return 处置强度（脚本参数可据此调整，如并发数、重试次数、资源额度）；
     *         0.5 表示默认强度（降级）
     */
    public double calculateIntensity(long taskId, String metric) {
        if (!enabled) return DEFAULT_INTENSITY;

        // 1) 读 threshold 数值（从 learning_profile）
        Double threshold = lookupThreshold(taskId, metric);
        if (threshold == null || threshold == 0) {
            log.debug("PID: no numeric threshold for task={} metric={} → default intensity", taskId, metric);
            return DEFAULT_INTENSITY;
        }

        // 2) 读最新 abnormal sample 做 observed
        Double observed = lookupLatestAbnormalSample(taskId, metric);
        if (observed == null) {
            log.debug("PID: no abnormal sample for task={} metric={} → default intensity", taskId, metric);
            return DEFAULT_INTENSITY;
        }

        // 3) 归一化误差
        double e = (observed - threshold) / Math.abs(threshold);

        PidState state = loadOrInit(taskId, metric);

        // 4) tooFrequent / 首次执行 → 跳过 I 项
        boolean tooFrequent = state.lastExecutedAt != null
                && Duration.between(state.lastExecutedAt, Instant.now()).toMinutes() < minIntervalMin;
        boolean firstExec = state.executionCount == 0;

        double pTerm = state.kp * e;
        double iTerm = (tooFrequent || firstExec) ? 0.0 : state.ki * state.integral;

        double intensity = clamp(pTerm + iTerm, 0.1, 1.0);

        // 5) 更新 last_error 和 last_intensity（积分项等 resolved 后积累）
        jdbc.update("""
                UPDATE sentinel_pid_state SET last_error=?, last_intensity=?, updated_at=CURRENT_TIMESTAMP
                WHERE task_id=? AND metric=?
                """, e, intensity, taskId, metric);

        log.info("PID intensity={} task={} metric={} e={} P={} I={} tooFrequent={} firstExec={} integral={}",
                round2(intensity), taskId, metric, round2(e), round2(pTerm), round2(iTerm),
                tooFrequent, firstExec, round2(state.integral));

        return intensity;
    }

    /**
     * 当告警被标记 resolved 时触发：读 resolved 后的指标回差，更新积分项。
     *
     * <p>调用点：AlertLifecycleService.resolveRecoveredAlerts() 等自动恢复路径。</p>
     */
    public void onAlertResolved(long taskId, String metric, Instant resolvedAt) {
        if (!enabled) return;

        // 1) 读 threshold
        Double threshold = lookupThreshold(taskId, metric);
        if (threshold == null || threshold == 0) return;

        // 2) 读 resolved 后第一个 sample
        Double resolvedValue = jdbc.queryForObject("""
                SELECT value_num FROM sentinel_metric_sample
                WHERE task_id=? AND metric=? AND sampled_at >= ?
                ORDER BY sampled_at ASC LIMIT 1
                """, Double.class, taskId, metric, java.sql.Timestamp.from(resolvedAt));

        if (resolvedValue == null) {
            log.debug("PID onAlertResolved: no post-resolution sample task={} metric={}", taskId, metric);
            return;
        }

        double errorAfter = (resolvedValue - threshold) / Math.abs(threshold);
        recordExecutionResult(taskId, metric, errorAfter);
    }

    /** 直接更新积分项（供 onAlertResolved 和外部反馈路径复用）。 */
    public void recordExecutionResult(long taskId, String metric, double errorAfter) {
        if (!enabled) return;

        PidState state = loadOrInit(taskId, metric);
        double newIntegral = clamp(decay * state.integral + errorAfter, -integralClamp, integralClamp);

        jdbc.update("""
                UPDATE sentinel_pid_state
                SET integral=?, last_error=?, last_executed_at=?, execution_count=execution_count+1,
                    updated_at=CURRENT_TIMESTAMP
                WHERE task_id=? AND metric=?
                """, newIntegral, errorAfter, java.sql.Timestamp.from(Instant.now()), taskId, metric);

        log.info("PID record result: task={} metric={} errorAfter={} integral={} (was {})",
                taskId, metric, round2(errorAfter), round2(newIntegral), round2(state.integral));
    }

    /* ── 数值查询 helpers ────────────────────────────────────────────────── */

    /** 从 sentinel_learning_profile 取数值阈值（suggested → current → null）。 */
    Double lookupThreshold(long taskId, String metric) {
        try {
            return jdbc.queryForObject("""
                    SELECT COALESCE(suggested_threshold, current_threshold)
                      FROM sentinel_learning_profile WHERE task_id=? AND metric=?
                    """, Double.class, taskId, metric);
        } catch (Exception e) {
            return null;
        }
    }

    /** 从 sentinel_metric_sample 取最新的 abnormal=TRUE 采样值。 */
    Double lookupLatestAbnormalSample(long taskId, String metric) {
        try {
            return jdbc.queryForObject("""
                    SELECT value_num FROM sentinel_metric_sample
                    WHERE task_id=? AND metric=? AND abnormal=TRUE
                    ORDER BY sampled_at DESC LIMIT 1
                    """, Double.class, taskId, metric);
        } catch (Exception e) {
            return null;
        }
    }

    /* ── 内部 ──────────────────────────────────────────────────────────── */

    private PidState loadOrInit(long taskId, String metric) {
        java.util.List<PidState> rows = jdbc.query("""
                SELECT kp, ki, kd, integral, last_error, last_intensity, last_executed_at,
                       execution_count, enabled
                FROM sentinel_pid_state WHERE task_id=? AND metric=?
                """, (rs, ignored) -> new PidState(
                        rs.getDouble("kp"),
                        rs.getDouble("ki"),
                        rs.getDouble("kd"),
                        rs.getDouble("integral"),
                        rs.getDouble("last_error"),
                        rs.getDouble("last_intensity"),
                        rs.getTimestamp("last_executed_at") != null
                                ? rs.getTimestamp("last_executed_at").toInstant() : null,
                        rs.getInt("execution_count"),
                        rs.getBoolean("enabled")),
                taskId, metric);

        if (!rows.isEmpty()) {
            PidState existing = rows.get(0);
            if (!existing.enabled) {
                log.debug("PID: disabled task={} metric={}", taskId, metric);
                return new PidState(kp, ki, 0.0, 0.0, 0.0, DEFAULT_INTENSITY, null, 0, false);
            }
            return existing;
        }

        // 首次：插入默认参数记录
        jdbc.update("""
                INSERT INTO sentinel_pid_state
                    (task_id, metric, kp, ki, kd, integral, last_error, last_intensity, enabled)
                VALUES (?, ?, ?, ?, 0.0, 0.0, 0.0, ?, 1)
                ON DUPLICATE KEY UPDATE task_id=VALUES(task_id)
                """, taskId, metric, kp, ki, DEFAULT_INTENSITY);
        return new PidState(kp, ki, 0.0, 0.0, 0.0, DEFAULT_INTENSITY, null, 0, true);
    }

    static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    static double round2(double v) {
        return Math.round(v * 100.0) / 100.0;
    }

    /** PID 运行时状态（与 DB 行解耦）。 */
    private record PidState(double kp, double ki, double kd, double integral,
                            double lastError, double lastIntensity, Instant lastExecutedAt,
                            int executionCount, boolean enabled) {}
}
