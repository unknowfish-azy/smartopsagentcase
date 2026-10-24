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
        new ResourceDatabasePopulator(new ClassPathResource("schema.sql")).execute(source);
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

    private record TestRuntime(String id, Long userId, Long sessionId) implements OperationRuntime {
        @Override public void write(String input) { }
        @Override public void resize(int columns, int rows) { }
        @Override public void onOutput(OutputListener listener) { }
        @Override public boolean isOpen() { return true; }
        @Override public void close() { }
    }
}
