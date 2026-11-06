package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRedactor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Service
public class OperationRunQueryService {
    private final JdbcTemplate jdbc;

    public OperationRunQueryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public RunPage list(Long userId, String traceId, String toolId, String status,
                        Instant startedFrom, Instant startedTo, int page, int pageSize) {
        int safePage = Math.max(1, page);
        int safePageSize = Math.max(1, Math.min(100, pageSize));
        List<Object> args = new ArrayList<>();
        String where = where(userId, traceId, toolId, status, startedFrom, startedTo, args);
        long total = jdbc.queryForObject("SELECT COUNT(*) FROM operation_run_record r " + where, Long.class, args.toArray());
        args.add(safePageSize);
        args.add((safePage - 1) * safePageSize);
        String sql = "SELECT r.id,r.trace_id,r.session_id,r.runtime_id,r.tool_id,r.status,r.started_at,r.ended_at," +
                "COUNT(o.id) command_count,COALESCE(SUM(CASE WHEN o.exit_code<>0 THEN 1 ELSE 0 END),0) failed_count " +
                "FROM operation_run_record r LEFT JOIN operation_run_output o ON o.run_id=r.id " + where +
                " GROUP BY r.id,r.trace_id,r.session_id,r.runtime_id,r.tool_id,r.status,r.started_at,r.ended_at " +
                "ORDER BY r.started_at DESC,r.id DESC LIMIT ? OFFSET ?";
        List<RunSummary> items = jdbc.query(sql, (rs, row) -> summary(
                rs.getLong("id"), rs.getString("trace_id"), (Long) rs.getObject("session_id"),
                rs.getString("runtime_id"), rs.getString("tool_id"), rs.getString("status"),
                instant(rs.getTimestamp("started_at")), instant(rs.getTimestamp("ended_at")),
                rs.getInt("command_count"), rs.getInt("failed_count")), args.toArray());
        return new RunPage(items, total, safePage, safePageSize);
    }

    public RunDetail detail(Long userId, Long id) {
        List<RunSummary> rows = jdbc.query(
                "SELECT r.id,r.trace_id,r.session_id,r.runtime_id,r.tool_id,r.status,r.started_at,r.ended_at," +
                        "COUNT(o.id) command_count,COALESCE(SUM(CASE WHEN o.exit_code<>0 THEN 1 ELSE 0 END),0) failed_count " +
                        "FROM operation_run_record r LEFT JOIN operation_run_output o ON o.run_id=r.id " +
                        "WHERE r.id=? AND r.user_id=? GROUP BY r.id,r.trace_id,r.session_id,r.runtime_id,r.tool_id,r.status,r.started_at,r.ended_at",
                (rs, row) -> summary(rs.getLong("id"), rs.getString("trace_id"), (Long) rs.getObject("session_id"),
                        rs.getString("runtime_id"), rs.getString("tool_id"), rs.getString("status"),
                        instant(rs.getTimestamp("started_at")), instant(rs.getTimestamp("ended_at")),
                        rs.getInt("command_count"), rs.getInt("failed_count")), id, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "OPERATION_RUN_NOT_FOUND");
        List<CommandOutput> outputs = jdbc.query(
                "SELECT id,sequence_no,command_text,exit_code,stdout_text,stderr_text,truncated,started_at,ended_at FROM operation_run_output WHERE run_id=? ORDER BY sequence_no,id",
                (rs, row) -> new CommandOutput(rs.getLong("id"), rs.getInt("sequence_no"),
                        OperationRedactor.redact(rs.getString("command_text")),
                        rs.getInt("exit_code"),
                        OperationRedactor.redact(text(rs.getString("stdout_text"))),
                        OperationRedactor.redact(text(rs.getString("stderr_text"))),
                        rs.getBoolean("truncated"),
                        instant(rs.getTimestamp("started_at")), instant(rs.getTimestamp("ended_at"))), id);
        List<Evidence> evidence = jdbc.query(
                "SELECT id,evidence_type,content,source_ref,created_at FROM operation_run_evidence WHERE run_id=? ORDER BY created_at,id",
                (rs, row) -> new Evidence(rs.getLong("id"), rs.getString("evidence_type"),
                        OperationRedactor.redact(rs.getString("content")),
                        rs.getString("source_ref"), instant(rs.getTimestamp("created_at"))), id);
        return new RunDetail(rows.get(0), outputs, evidence);
    }

    /**
     * 人工核验一次 UNCERTAIN 的运行结果。
     *
     * <p>只有 UNCERTAIN 才允许核验：它表示"执行中断、远端是否已生效未知"。
     * 核验后落到 {@code VERIFIED_SUCCEEDED} / {@code VERIFIED_FAILED}，
     * 与普通失败区分开，避免把未核实的写操作当成安全可重试的失败。</p>
     */
    public RunDetail verify(Long userId, Long runId, String decision, String note) {
        String normalized = decision == null ? "" : decision.trim().toUpperCase();
        if (!"DONE".equals(normalized) && !"NOT_DONE".equals(normalized)) {
            throw new BusinessException(400, "OPERATION_RUN_VERIFY_DECISION_INVALID");
        }
        String evidence = note == null ? "" : note.trim();
        if (evidence.isEmpty()) throw new BusinessException(400, "OPERATION_RUN_VERIFY_NOTE_REQUIRED");
        if (evidence.length() > 500) throw new BusinessException(400, "OPERATION_RUN_VERIFY_NOTE_TOO_LONG");

        String target = "DONE".equals(normalized) ? "VERIFIED_SUCCEEDED" : "VERIFIED_FAILED";
        int updated = jdbc.update(
                "UPDATE operation_run_record SET status=? WHERE id=? AND user_id=? AND status='UNCERTAIN'",
                target, runId, userId);
        if (updated == 0) {
            List<String> statuses = jdbc.query("SELECT status FROM operation_run_record WHERE id=? AND user_id=?",
                    (rs, row) -> rs.getString("status"), runId, userId);
            if (statuses.isEmpty()) throw new BusinessException(404, "OPERATION_RUN_NOT_FOUND");
            throw new BusinessException(409, "OPERATION_RUN_NOT_UNCERTAIN");
        }
        jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                runId, "RUN_VERIFIED",
                OperationRedactor.redact("人工核验结论=" + normalized + "；依据：" + evidence + "；不自动重试写操作"),
                "human-verification", Timestamp.from(Instant.now()));
        return detail(userId, runId);
    }

    /**
     * 请求取消一次仍在执行的 Run。
     *
     * <p>取消是"协作式"的：只置标记，由执行循环在命令之间读取并停止派发后续命令。
     * 不会中断已在远端执行的命令，因为强制中断同样会让结果处于未知状态。</p>
     */
    public void requestCancel(Long userId, Long runId) {
        int updated = jdbc.update(
                "UPDATE operation_run_record SET cancel_requested=1 WHERE id=? AND user_id=? AND status='RUNNING'",
                runId, userId);
        if (updated == 0) {
            List<String> statuses = jdbc.query("SELECT status FROM operation_run_record WHERE id=? AND user_id=?",
                    (rs, row) -> rs.getString("status"), runId, userId);
            if (statuses.isEmpty()) throw new BusinessException(404, "OPERATION_RUN_NOT_FOUND");
            throw new BusinessException(409, "OPERATION_RUN_NOT_CANCELLABLE");
        }
    }

    private String where(Long userId, String traceId, String toolId, String status,
                         Instant from, Instant to, List<Object> args) {
        StringBuilder sql = new StringBuilder("WHERE r.user_id=?");
        args.add(userId);
        if (hasText(traceId)) { sql.append(" AND LOWER(r.trace_id) LIKE ?"); args.add("%" + traceId.trim().toLowerCase() + "%"); }
        if (hasText(toolId)) { sql.append(" AND r.tool_id=?"); args.add(toolId.trim()); }
        if (hasText(status)) { sql.append(" AND r.status=?"); args.add(status.trim()); }
        if (from != null) { sql.append(" AND r.started_at>=?"); args.add(Timestamp.from(from)); }
        if (to != null) { sql.append(" AND r.started_at<=?"); args.add(Timestamp.from(to)); }
        return sql.toString();
    }

    private RunSummary summary(Long id, String traceId, Long sessionId, String runtimeId, String toolId,
                               String status, Instant startedAt, Instant endedAt, int commands, int failed) {
        return new RunSummary(id, traceId, sessionId, runtimeId, toolId, status, startedAt, endedAt, commands, failed);
    }
    private static boolean hasText(String value) { return value != null && !value.isBlank(); }
    private static Instant instant(Timestamp value) { return value == null ? null : value.toInstant(); }
    private static String text(String value) { return value == null ? "" : value; }

    public record RunPage(List<RunSummary> items, long total, int page, int pageSize) {}
    public record RunSummary(Long id, String traceId, Long sessionId, String runtimeId, String toolId, String status,
                             Instant startedAt, Instant endedAt, int commandCount, int failedCommandCount) {}
    public record RunDetail(RunSummary run, List<CommandOutput> outputs, List<Evidence> evidence) {}
    public record CommandOutput(Long id, int sequenceNo, String command, int exitCode, String stdout, String stderr,
                                boolean truncated, Instant startedAt, Instant endedAt) {}
    public record Evidence(Long id, String type, String content, String sourceRef, Instant createdAt) {}
}
