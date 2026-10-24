package com.smartops.service;

import com.smartops.operations.OperationRuntime;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;

import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.time.Instant;

@Service
public class JdbcOperationRunRecorder implements OperationRunRecorder {
    private final JdbcTemplate jdbc;

    public JdbcOperationRunRecorder(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public RunHandle start(String traceId, Long userId, OperationRuntime runtime, String toolId, Instant startedAt) {
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO operation_run_record(trace_id,user_id,session_id,runtime_id,tool_id,status,started_at) VALUES(?,?,?,?,?,'RUNNING',?)",
                    new String[]{"id"});
            statement.setString(1, traceId);
            statement.setLong(2, userId);
            if (runtime.sessionId() == null) statement.setNull(3, java.sql.Types.BIGINT);
            else statement.setLong(3, runtime.sessionId());
            statement.setString(4, runtime.id());
            statement.setString(5, toolId);
            statement.setTimestamp(6, Timestamp.from(startedAt));
            return statement;
        }, keys);
        Number id = keys.getKey();
        if (id == null) throw new IllegalStateException("RUN_RECORD_ID_MISSING");
        return new RunHandle(id.longValue(), traceId);
    }

    @Override
    public void recordCommand(RunHandle run, int sequence, String command, int exitCode,
                              String stdout, String stderr, Instant startedAt, Instant endedAt) {
        jdbc.update("INSERT INTO operation_run_output(run_id,sequence_no,command_text,exit_code,stdout_text,stderr_text,started_at,ended_at) VALUES(?,?,?,?,?,?,?,?)",
                run.id(), sequence, command, exitCode, stdout, stderr,
                Timestamp.from(startedAt), Timestamp.from(endedAt));
        jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                run.id(), "COMMAND_RESULT", "exitCode=" + exitCode, "command:" + sequence,
                Timestamp.from(endedAt));
    }

    @Override
    public void finish(RunHandle run, String status, Instant endedAt) {
        jdbc.update("UPDATE operation_run_record SET status=?, ended_at=? WHERE id=?",
                status, Timestamp.from(endedAt), run.id());
    }
}
