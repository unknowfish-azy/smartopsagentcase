package com.smartops.service;

import com.smartops.operations.OperationRuntime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class JdbcOperationRunRecorderTest {
    private JdbcTemplate jdbc;
    private JdbcOperationRunRecorder recorder;

    @BeforeEach
    void setUp() {
        var source = new DriverManagerDataSource(
                "jdbc:h2:mem:operation-run-" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1",
                "sa",
                ""
        );
        // 基础表由 schema.sql 建立，治理列（幂等键/租约/预算/取消）来自正式迁移，
        // 让单元测试与真实升级路径保持同一份 DDL，而不是另维护一套测试表结构。
        new ResourceDatabasePopulator(
                new ClassPathResource("schema.sql"),
                new ClassPathResource("db/migration/V20261105.2__operation_run_governance.sql")
        ).execute(source);
        jdbc = new JdbcTemplate(source);
        recorder = new JdbcOperationRunRecorder(jdbc);
    }

    @Test
    void persists_run_output_evidence_and_final_status_under_one_trace() {
        Instant runStarted = Instant.parse("2026-09-27T01:00:00Z");
        Instant commandStarted = Instant.parse("2026-09-27T01:00:01Z");
        Instant commandEnded = Instant.parse("2026-09-27T01:00:03Z");
        Instant runEnded = Instant.parse("2026-09-27T01:00:04Z");

        OperationRunRecorder.RunHandle run = recorder.start(
                "trace-001",
                7L,
                new TestRuntime("runtime-9", 7L, 23L),
                "docker-logs",
                runStarted
        );
        recorder.recordCommand(
                run,
                1,
                "docker logs --tail 200 api",
                17,
                "application output",
                "container exited",
                commandStarted,
                commandEnded
        );
        recorder.finish(run, "FAILED", runEnded);

        assertThat(jdbc.queryForMap("SELECT * FROM operation_run_record WHERE id=?", run.id()))
                .containsEntry("TRACE_ID", "trace-001")
                .containsEntry("USER_ID", 7L)
                .containsEntry("SESSION_ID", 23L)
                .containsEntry("RUNTIME_ID", "runtime-9")
                .containsEntry("TOOL_ID", "docker-logs")
                .containsEntry("STATUS", "FAILED");

        assertThat(jdbc.queryForMap("SELECT * FROM operation_run_output WHERE run_id=?", run.id()))
                .containsEntry("SEQUENCE_NO", 1)
                .containsEntry("COMMAND_TEXT", "docker logs --tail 200 api")
                .containsEntry("EXIT_CODE", 17)
                .containsEntry("STDOUT_TEXT", "application output")
                .containsEntry("STDERR_TEXT", "container exited");

        assertThat(jdbc.queryForMap("SELECT * FROM operation_run_evidence WHERE run_id=?", run.id()))
                .containsEntry("EVIDENCE_TYPE", "COMMAND_RESULT")
                .containsEntry("CONTENT", "exitCode=17")
                .containsEntry("SOURCE_REF", "command:1");
    }

    @Test
    void duplicate_idempotency_key_is_rejected_instead_of_reexecuted() {
        Instant startedAt = Instant.parse("2026-11-05T02:00:00Z");
        OperationRunRecorder.RunSpec spec = new OperationRunRecorder.RunSpec(
                "trace-idem", 7L, new TestRuntime("runtime-9", 7L, 23L), "service-restart",
                "team-run:42", startedAt, startedAt.plusSeconds(120), 1024, 60_000);
        recorder.start(spec);

        // 同一审批单二次执行必须被拒绝，否则写操作会产生重复副作用
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> recorder.start(spec))
                .isInstanceOf(com.smartops.exception.BusinessException.class)
                .hasMessageContaining("OPERATION_RUN_ALREADY_EXECUTED");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM operation_run_record", Integer.class)).isEqualTo(1);
    }

    @Test
    void cancel_flag_and_output_budget_are_persisted_as_evidence() {
        Instant startedAt = Instant.parse("2026-11-05T03:00:00Z");
        OperationRunRecorder.RunHandle run = recorder.start(
                "trace-budget", 7L, new TestRuntime("runtime-9", 7L, 23L), "system-logs", startedAt);

        jdbc.update("UPDATE operation_run_record SET cancel_requested=TRUE WHERE id=?", run.id());
        assertThat(recorder.cancelRequested(run)).isTrue();

        recorder.recordCommand(run, 1, "journalctl -n 200", 0, "x".repeat(100), "", startedAt,
                startedAt.plusSeconds(1), true);

        assertThat(jdbc.queryForObject("SELECT truncated FROM operation_run_output WHERE run_id=?",
                Boolean.class, run.id())).isTrue();
        assertThat(jdbc.queryForList(
                "SELECT evidence_type FROM operation_run_evidence WHERE run_id=?", String.class, run.id()))
                .contains("OUTPUT_TRUNCATED");
    }

    @Test
    void stale_run_becomes_uncertain_and_is_never_auto_retried() {
        Instant startedAt = Instant.parse("2026-11-05T04:00:00Z");
        OperationRunRecorder.RunHandle run = recorder.start(
                "trace-stale", 7L, new TestRuntime("runtime-9", 7L, 23L), "service-restart", startedAt);
        // 心跳停在很久之前，模拟执行进程消失
        jdbc.update("UPDATE operation_run_record SET heartbeat_at=?, lease_expires_at=? WHERE id=?",
                java.sql.Timestamp.from(startedAt),
                java.sql.Timestamp.from(startedAt.plusSeconds(30)), run.id());

        int recovered = new OperationRunRecoveryScheduler(jdbc, 90_000L)
                .recoverOnce(startedAt.plusSeconds(600));

        assertThat(recovered).isEqualTo(1);
        assertThat(jdbc.queryForMap("SELECT * FROM operation_run_record WHERE id=?", run.id()))
                .containsEntry("STATUS", "UNCERTAIN");
        assertThat(jdbc.queryForList(
                "SELECT evidence_type FROM operation_run_evidence WHERE run_id=?", String.class, run.id()))
                .contains("RUN_STALE");
    }

    private record TestRuntime(String id, Long userId, Long sessionId) implements OperationRuntime {
        @Override public void write(String input) { }
        @Override public void resize(int columns, int rows) { }
        @Override public void onOutput(OutputListener listener) { }
        @Override public boolean isOpen() { return true; }
        @Override public void close() { }
    }
}
