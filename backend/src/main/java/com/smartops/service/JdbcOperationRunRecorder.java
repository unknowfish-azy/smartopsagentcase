package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRedactor;
import com.smartops.operations.OperationRuntime;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;

import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.time.Instant;

/**
 * operation_run_record 的 JDBC 实现。
 *
 * <p>新增列（幂等键、attempt、租约、心跳、绝对 deadline、输出字节数、取消标记）
 * 由 Flyway 迁移补齐；这里不再做“缺列时静默降级”，因为缺列会让恢复语义失真。
 */
@Service
public class JdbcOperationRunRecorder implements OperationRunRecorder {
    /** 单次运行默认绝对预算：超过即 TIMEOUT，不再逐条命令无限延长。 */
    public static final long DEFAULT_DEADLINE_MS = 120_000L;
    /** 默认租约：超过该时长无心跳，恢复扫描会把它标记为悬挂。 */
    public static final long DEFAULT_LEASE_MS = 60_000L;

    private final JdbcTemplate jdbc;

    public JdbcOperationRunRecorder(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public RunHandle start(String traceId, Long userId, OperationRuntime runtime, String toolId, Instant startedAt) {
        return start(new RunSpec(traceId, userId, runtime, toolId, null, startedAt,
                startedAt.plusMillis(DEFAULT_DEADLINE_MS), 512 * 1024, DEFAULT_LEASE_MS));
    }

    @Override
    public RunHandle start(RunSpec spec) {
        String idempotencyKey = blankToNull(spec.idempotencyKey());
        if (idempotencyKey != null) {
            // 幂等键在同一用户内唯一：已存在说明这次请求此前已经启动过。
            // 拒绝重跑，而不是“第二次当成一次新执行”，否则写操作可能产生重复副作用。
            jdbc.query("SELECT id,trace_id FROM operation_run_record WHERE user_id=? AND idempotency_key=? LIMIT 1",
                    (row, ignored) -> row.getLong("id"), spec.userId(), idempotencyKey)
                    .stream().findFirst()
                    .ifPresent(existing -> {
                        throw new BusinessException(409, "OPERATION_RUN_ALREADY_EXECUTED");
                    });
        }
        Instant startedAt = spec.startedAt();
        Instant deadlineAt = spec.deadlineAt() == null ? startedAt.plusMillis(DEFAULT_DEADLINE_MS) : spec.deadlineAt();
        long leaseMs = spec.leaseMs() <= 0 ? DEFAULT_LEASE_MS : spec.leaseMs();
        KeyHolder keys = new GeneratedKeyHolder();
        try {
            jdbc.update(connection -> {
                PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO operation_run_record(trace_id,user_id,session_id,runtime_id,tool_id,status,started_at,"
                                + "idempotency_key,attempt,deadline_at,lease_expires_at,heartbeat_at,cancel_requested,output_bytes) "
                                + "VALUES(?,?,?,?,?,'RUNNING',?,?,1,?,?,?,0,0)",
                        new String[]{"id"});
                statement.setString(1, spec.traceId());
                statement.setLong(2, spec.userId());
                if (spec.runtime().sessionId() == null) statement.setNull(3, java.sql.Types.BIGINT);
                else statement.setLong(3, spec.runtime().sessionId());
                statement.setString(4, spec.runtime().id());
                statement.setString(5, spec.toolId());
                statement.setTimestamp(6, Timestamp.from(startedAt));
                if (idempotencyKey == null) statement.setNull(7, java.sql.Types.VARCHAR);
                else statement.setString(7, idempotencyKey);
                statement.setTimestamp(8, Timestamp.from(deadlineAt));
                statement.setTimestamp(9, Timestamp.from(startedAt.plusMillis(leaseMs)));
                statement.setTimestamp(10, Timestamp.from(startedAt));
                return statement;
            }, keys);
        } catch (DuplicateKeyException raced) {
            // 并发请求同时通过上面的存在性检查时，唯一索引兜底。
            throw new BusinessException(409, "OPERATION_RUN_ALREADY_EXECUTED");
        }
        Number id = keys.getKey();
        if (id == null) throw new IllegalStateException("RUN_RECORD_ID_MISSING");
        return new RunHandle(id.longValue(), spec.traceId());
    }

    @Override
    public void recordCommand(RunHandle run, int sequence, String command, int exitCode,
                              String stdout, String stderr, Instant startedAt, Instant endedAt) {
        recordCommand(run, sequence, command, exitCode, stdout, stderr, startedAt, endedAt, false);
    }

    @Override
    public void recordCommand(RunHandle run, int sequence, String command, int exitCode,
                              String stdout, String stderr, Instant startedAt, Instant endedAt, boolean truncated) {
        // SEC-11：命令与输出是凭据泄漏最大面（env / cat .env / docker inspect），
        // 写库前统一遮蔽，避免 API 读回明文。
        jdbc.update("INSERT INTO operation_run_output(run_id,sequence_no,command_text,exit_code,stdout_text,stderr_text,"
                        + "started_at,ended_at,truncated,output_bytes) VALUES(?,?,?,?,?,?,?,?,?,?)",
                run.id(), sequence, OperationRedactor.redact(command), exitCode,
                OperationRedactor.redact(stdout), OperationRedactor.redact(stderr),
                Timestamp.from(startedAt), Timestamp.from(endedAt), truncated,
                byteLength(stdout) + byteLength(stderr));
        jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                run.id(), "COMMAND_RESULT",
                OperationRedactor.redact("exitCode=" + exitCode + (truncated ? ";output=TRUNCATED" : "")),
                "command:" + sequence, Timestamp.from(endedAt));
        if (truncated) {
            jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                    run.id(), "OUTPUT_TRUNCATED", "输出超过单条命令预算，已截断；完整输出未落库", "command:" + sequence,
                    Timestamp.from(endedAt));
        }
        jdbc.update("UPDATE operation_run_record SET output_bytes=output_bytes+? WHERE id=?",
                byteLength(stdout) + byteLength(stderr), run.id());
    }

    @Override
    public void finish(RunHandle run, String status, Instant endedAt) {
        jdbc.update("UPDATE operation_run_record SET status=?, ended_at=?, lease_expires_at=NULL WHERE id=?",
                status, Timestamp.from(endedAt), run.id());
        if ("UNCERTAIN".equals(status)) {
            // 远端动作是否落地未知：不自动重试，必须由人核验远端实际状态。
            recordEvidence(run, "RUN_UNCERTAIN", "执行中断且远端状态未知；不得直接重试写操作，需人工核验后再决定");
        }
    }

    @Override
    public void recordBlockedAttempt(String traceId, Long userId, String runtimeId, String toolId,
                                     String status, String reason, Instant at) {
        // 未真正执行的调用直接以终态落库：不建 RUNNING、不占租约，恢复扫描不会误判为悬挂。
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO operation_run_record(trace_id,user_id,session_id,runtime_id,tool_id,status,"
                            + "started_at,ended_at) VALUES(?,?,NULL,?,?,?,?,?)",
                    new String[]{"id"});
            statement.setString(1, traceId);
            statement.setLong(2, userId);
            statement.setString(3, runtimeId == null ? "" : runtimeId);
            statement.setString(4, toolId);
            statement.setString(5, status);
            statement.setTimestamp(6, Timestamp.from(at));
            statement.setTimestamp(7, Timestamp.from(at));
            return statement;
        }, keys);
        Number id = keys.getKey();
        if (id == null) throw new IllegalStateException("RUN_RECORD_ID_MISSING");
        jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                id.longValue(), "TOOL_BLOCKED", reason, "tool:" + toolId, Timestamp.from(at));
    }

    @Override
    public void heartbeat(RunHandle run) {
        Instant now = Instant.now();
        jdbc.update("UPDATE operation_run_record SET heartbeat_at=?, lease_expires_at=? WHERE id=? AND status='RUNNING'",
                Timestamp.from(now), Timestamp.from(now.plusMillis(DEFAULT_LEASE_MS)), run.id());
    }

    @Override
    public boolean cancelRequested(RunHandle run) {
        Boolean requested = jdbc.queryForObject(
                "SELECT cancel_requested FROM operation_run_record WHERE id=?", Boolean.class, run.id());
        return Boolean.TRUE.equals(requested);
    }

    @Override
    public void recordEvidence(RunHandle run, String type, String content) {
        jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                run.id(), type, OperationRedactor.redact(content), null, Timestamp.from(Instant.now()));
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static long byteLength(String value) {
        return value == null ? 0L : value.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
    }
}
