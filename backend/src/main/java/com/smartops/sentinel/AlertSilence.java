package com.smartops.sentinel;

import org.springframework.jdbc.core.JdbcTemplate;

import java.time.Instant;

/**
 * 静默窗口判定。
 *
 * <p>做成静态工具是因为判定点分散在"建告警"和"发通知"两处，
 * 而这两处一个在 {@link SentinelService} 的轮询里、一个在人工通知里，
 * 共用同一份 SQL 才不会出现"告警被静默了但通知照发"的裂缝。</p>
 */
public final class AlertSilence {

    private AlertSilence() {
    }

    /** 给定时刻，该任务是否处于静默/维护窗口。 */
    public static boolean isActive(JdbcTemplate jdbc, Long taskId, Instant at) {
        if (taskId == null) {
            return false;
        }
        java.sql.Timestamp moment = java.sql.Timestamp.from(at);
        Integer count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM sentinel_silence
                 WHERE starts_at <= ? AND ends_at >= ?
                   AND COALESCE(status, 'ACTIVE') = 'ACTIVE'
                   AND (scope_type='GLOBAL' OR (scope_type='TASK' AND scope_id=?))
                """, Integer.class, moment, moment, taskId);
        return count != null && count > 0;
    }
}
