package com.smartops.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

/**
 * OPS-04：悬挂 Run 恢复扫描。
 *
 * <p>判断依据是租约与心跳，而不是"启动时间过了多久"：
 * 仍在执行的 Run 会持续刷新 heartbeat_at，只有长时间没有心跳的才会被判为悬挂。</p>
 *
 * <p><b>不自动重试</b>：悬挂意味着"进程消失了，但远端是否已执行未知"。
 * 把它标成 UNCERTAIN 并留下核验证据，比自动重跑一个可能已经生效的写操作安全。</p>
 */
@Component
public class OperationRunRecoveryScheduler {
    private static final Logger log = LoggerFactory.getLogger(OperationRunRecoveryScheduler.class);

    private final JdbcTemplate jdbc;
    private final long staleMs;

    public OperationRunRecoveryScheduler(JdbcTemplate jdbc,
                                         @Value("${smartops.operations.run.recovery-stale-ms:90000}") long staleMs) {
        this.jdbc = jdbc;
        this.staleMs = staleMs;
    }

    @Scheduled(fixedDelayString = "${smartops.operations.run.recovery-interval-ms:60000}",
            initialDelayString = "${smartops.operations.run.recovery-initial-delay-ms:30000}")
    public void recoverStaleRuns() {
        int recovered = recoverOnce(Instant.now());
        if (recovered > 0) log.warn("recovered stale operation runs count={}", recovered);
    }

    /** 返回本次被判定为悬挂的 Run 数量，便于测试直接断言。 */
    public int recoverOnce(Instant now) {
        Instant cutoff = now.minusMillis(staleMs);
        List<Long> ids = jdbc.query(
                "SELECT id FROM operation_run_record WHERE status='RUNNING' "
                        + "AND (heartbeat_at IS NULL OR heartbeat_at < ?) "
                        + "AND (lease_expires_at IS NULL OR lease_expires_at < ?)",
                (rs, row) -> rs.getLong("id"), Timestamp.from(cutoff), Timestamp.from(cutoff));
        int recovered = 0;
        for (Long id : ids) {
            // 条件更新兜底：扫描与心跳可能并发，只有仍然超时的记录才会被改判。
            int updated = jdbc.update(
                    "UPDATE operation_run_record SET status='UNCERTAIN', ended_at=?, lease_expires_at=NULL "
                            + "WHERE id=? AND status='RUNNING' AND (heartbeat_at IS NULL OR heartbeat_at < ?)",
                    Timestamp.from(now), id, Timestamp.from(cutoff));
            if (updated == 0) continue;
            recovered++;
            jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                    id, "RUN_STALE",
                    "租约到期且无心跳，进程可能已消失；远端动作是否生效未知，禁止自动重试，需人工核验",
                    "recovery-scheduler", Timestamp.from(now));
        }
        return recovered;
    }
}
