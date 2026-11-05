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
 * OPS-04：审批消费后中断的对账扫描。
 *
 * <p>团队执行的顺序是「审批 → consumeGrant → 执行 → finish」。若进程在
 * consumeGrant 之后、finish 之前消失，<b>授权已被消费</b>，但团队运行还停在 RUNNING：
 * 既不能重新审批，也不能自动重跑（远端可能已执行）。</p>
 *
 * <p>这里按幂等键 {@code tool-run:<userId>:team-run:<runId>} 找到对应的 Java Run，
 * 用它的事实回填团队运行状态；找不到任何 Run 时置为 UNCERTAIN 并等待人工核验，
 * 而不是猜成失败或成功。</p>
 */
@Component
public class TeamAgentRunRecoveryScheduler {
    private static final Logger log = LoggerFactory.getLogger(TeamAgentRunRecoveryScheduler.class);

    private final JdbcTemplate jdbc;
    private final long staleMs;

    public TeamAgentRunRecoveryScheduler(JdbcTemplate jdbc,
                                         @Value("${smartops.operations.team-run.recovery-stale-ms:600000}") long staleMs) {
        this.jdbc = jdbc;
        this.staleMs = staleMs;
    }

    @Scheduled(fixedDelayString = "${smartops.operations.team-run.recovery-interval-ms:120000}",
            initialDelayString = "${smartops.operations.team-run.recovery-initial-delay-ms:60000}")
    public void recoverStaleTeamRuns() {
        int recovered = recoverOnce(Instant.now());
        if (recovered > 0) log.warn("reconciled stale team runs count={}", recovered);
    }

    /** 返回本次完成对账的团队运行数量，便于测试直接断言。 */
    public int recoverOnce(Instant now) {
        Instant cutoff = now.minusMillis(staleMs);
        List<TeamRun> runs = jdbc.query(
                "SELECT id,requester_id FROM team_agent_run WHERE status='RUNNING' AND created_at < ?",
                (rs, row) -> new TeamRun(rs.getLong("id"), rs.getLong("requester_id")), Timestamp.from(cutoff));
        int recovered = 0;
        for (TeamRun run : runs) {
            String idempotencyKey = "tool-run:" + run.requesterId() + ":team-run-" + run.id();
            List<OperationRun> operations = jdbc.query(
                    "SELECT id,status FROM operation_run_record WHERE user_id=? AND idempotency_key=?",
                    (rs, row) -> new OperationRun(rs.getLong("id"), rs.getString("status")), run.requesterId(), idempotencyKey);
            String teamStatus;
            if (operations.isEmpty()) {
                // 授权已消费但没有任何执行记录：远端动作是否发生未知，必须人工核验。
                teamStatus = "UNCERTAIN";
            } else {
                OperationRun operation = operations.get(0);
                if ("RUNNING".equals(operation.status())) continue;
                teamStatus = switch (operation.status()) {
                    case "SUCCEEDED", "VERIFIED_SUCCEEDED" -> "SUCCEEDED";
                    case "FAILED", "VERIFIED_FAILED" -> "FAILED";
                    default -> "UNCERTAIN";
                };
                jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                        operation.id(), "TEAM_RUN_RECONCILED",
                        "团队运行 #" + run.id() + " 由 Run 事实回填为 " + teamStatus + "；审批已消费，禁止自动重跑",
                        "team-run-recovery", Timestamp.from(now));
            }
            int updated = jdbc.update("UPDATE team_agent_run SET status=? WHERE id=? AND status='RUNNING'",
                    teamStatus, run.id());
            if (updated == 0) continue;
            recovered++;
        }
        return recovered;
    }

    private record TeamRun(long id, long requesterId) {}

    private record OperationRun(long id, String status) {}
}
