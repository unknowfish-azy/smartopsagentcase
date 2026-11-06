package com.smartops.service;

import com.smartops.operations.OperationRuntime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/** SEC-11 / TM-30：工具输出在写库与读回两个边界都必须脱敏。 */
class OperationOutputRedactionTest {
    private JdbcTemplate jdbc;
    private JdbcOperationRunRecorder recorder;
    private OperationRunQueryService query;

    @BeforeEach
    void setUp() {
        var source = new DriverManagerDataSource(
                "jdbc:h2:mem:operation-redact-" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        new ResourceDatabasePopulator(
                new ClassPathResource("schema.sql"),
                new ClassPathResource("db/migration/V20261105.2__operation_run_governance.sql")
        ).execute(source);
        jdbc = new JdbcTemplate(source);
        recorder = new JdbcOperationRunRecorder(jdbc);
        query = new OperationRunQueryService(jdbc);
    }

    @Test
    void redacts_secrets_before_persisting_tool_output_and_before_returning_it() {
        Instant startedAt = Instant.parse("2026-11-05T05:00:00Z");
        OperationRunRecorder.RunHandle run = recorder.start(
                "trace-redact", 7L, new TestRuntime("runtime-9", 7L, 23L), "host-health", startedAt);

        recorder.recordCommand(run, 1, "env | sort", 0,
                "API_TOKEN=abc123\nAuthorization: Bearer xyz-789",
                "DB_PASSWORD=hunter2", startedAt, startedAt.plusSeconds(1));
        recorder.recordEvidence(run, "HOST_CHECK", "cookie: session=secret-cookie");
        recorder.finish(run, "SUCCEEDED", startedAt.plusSeconds(2));

        assertThat(jdbc.queryForObject("SELECT stdout_text FROM operation_run_output WHERE run_id=?",
                String.class, run.id()))
                .doesNotContain("abc123", "xyz-789")
                .contains("[REDACTED]");
        assertThat(jdbc.queryForObject("SELECT stderr_text FROM operation_run_output WHERE run_id=?",
                String.class, run.id()))
                .doesNotContain("hunter2")
                .contains("[REDACTED]");

        var detail = query.detail(7L, run.id());
        assertThat(detail.outputs().get(0).stdout())
                .doesNotContain("abc123", "xyz-789")
                .contains("[REDACTED]");
        assertThat(detail.evidence()).extracting(OperationRunQueryService.Evidence::content)
                .noneMatch(content -> content.contains("secret-cookie"));
    }

    @Test
    void masks_secrets_in_historical_rows_on_read() {
        long runId = insertRun("trace-legacy-secret", 7L);
        jdbc.update("INSERT INTO operation_run_output(run_id,sequence_no,command_text,exit_code,stdout_text,stderr_text,"
                        + "started_at,ended_at) VALUES(?,?,?,?,?,?,?,?)",
                runId, 1, "env", 0, "API_TOKEN=abc123", "authorization: Bearer xyz-789",
                Timestamp.from(Instant.parse("2026-11-05T05:00:00Z")),
                Timestamp.from(Instant.parse("2026-11-05T05:00:01Z")));

        var detail = query.detail(7L, runId);

        assertThat(detail.outputs().get(0).stdout()).doesNotContain("abc123").contains("[REDACTED]");
        assertThat(detail.outputs().get(0).stderr()).doesNotContain("xyz-789").contains("[REDACTED]");
    }

    private long insertRun(String traceId, long userId) {
        jdbc.update("INSERT INTO operation_run_record(trace_id,user_id,runtime_id,tool_id,status,started_at,ended_at) "
                        + "VALUES(?,?,?,?,?,?,?)",
                traceId, userId, "runtime-1", "host-health", "SUCCEEDED",
                Timestamp.from(Instant.parse("2026-11-05T05:00:00Z")),
                Timestamp.from(Instant.parse("2026-11-05T05:00:05Z")));
        return jdbc.queryForObject("SELECT id FROM operation_run_record WHERE trace_id=?", Long.class, traceId);
    }

    private record TestRuntime(String id, Long userId, Long sessionId) implements OperationRuntime {
        @Override public void write(String input) { }
        @Override public void resize(int columns, int rows) { }
        @Override public void onOutput(OutputListener listener) { }
        @Override public boolean isOpen() { return true; }
        @Override public void close() { }
    }
}
