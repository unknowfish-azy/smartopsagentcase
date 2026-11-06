package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OperationRunQueryServiceTest {
    private JdbcTemplate jdbc;
    private OperationRunQueryService service;

    @BeforeEach
    void setUp() {
        var dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:run-query-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE operation_run_record (id BIGINT AUTO_INCREMENT PRIMARY KEY, trace_id VARCHAR(64) NOT NULL, user_id BIGINT NOT NULL, session_id BIGINT, runtime_id VARCHAR(128) NOT NULL, tool_id VARCHAR(128) NOT NULL, status VARCHAR(32) NOT NULL, started_at TIMESTAMP NOT NULL, ended_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        jdbc.execute("CREATE TABLE operation_run_output (id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NOT NULL, sequence_no INT NOT NULL, command_text CLOB NOT NULL, exit_code INT NOT NULL, stdout_text CLOB, stderr_text CLOB, truncated TINYINT(1) NOT NULL DEFAULT 0, output_bytes BIGINT NOT NULL DEFAULT 0, started_at TIMESTAMP NOT NULL, ended_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE operation_run_evidence (id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NOT NULL, evidence_type VARCHAR(64) NOT NULL, content CLOB NOT NULL, source_ref VARCHAR(255), created_at TIMESTAMP NOT NULL)");
        service = new OperationRunQueryService(jdbc);
    }

    @Test
    void listsOnlyCurrentUserAndAppliesFiltersAndPaging() {
        long older = insertRun("trace-linux-old", 1, "linux.process", "SUCCESS", "2026-09-27T01:00:00Z");
        long newest = insertRun("trace-linux-new", 1, "linux.process", "FAILED", "2026-09-27T03:00:00Z");
        insertRun("trace-other-user", 2, "linux.process", "FAILED", "2026-09-27T04:00:00Z");
        insertRun("trace-docker", 1, "docker.ps", "SUCCESS", "2026-09-27T02:00:00Z");
        insertOutput(newest, 1, 1, "", "permission denied");
        insertOutput(newest, 2, 0, "ok", "");

        var page = service.list(1L, "linux", "linux.process", "FAILED",
                Instant.parse("2026-09-27T00:00:00Z"), Instant.parse("2026-09-28T00:00:00Z"), 1, 20);

        assertThat(page.total()).isEqualTo(1);
        assertThat(page.items()).extracting(OperationRunQueryService.RunSummary::id).containsExactly(newest);
        assertThat(page.items().get(0).commandCount()).isEqualTo(2);
        assertThat(page.items().get(0).failedCommandCount()).isEqualTo(1);

        var ordered = service.list(1L, null, null, null, null, null, 1, 2);
        assertThat(ordered.items()).extracting(OperationRunQueryService.RunSummary::id)
                .containsExactly(newest, jdbc.queryForObject("SELECT id FROM operation_run_record WHERE trace_id='trace-docker'", Long.class));
        assertThat(ordered.total()).isEqualTo(3);
        assertThat(older).isPositive();
    }

    @Test
    void clampsPageAndPageSizeToSafeBounds() {
        insertRun("trace-one", 1, "linux.uptime", "SUCCESS", "2026-09-27T01:00:00Z");
        var page = service.list(1L, null, null, null, null, null, 0, 1000);
        assertThat(page.page()).isEqualTo(1);
        assertThat(page.pageSize()).isEqualTo(100);
    }

    @Test
    void loadsOwnedDetailWithOrderedOutputsAndEvidence() {
        long run = insertRun("trace-detail", 1, "k8s.pods", "SUCCESS", "2026-09-27T01:00:00Z");
        insertOutput(run, 2, 0, "second", "");
        insertOutput(run, 1, 0, "", "");
        jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                run, "COMMAND_RESULT", "later", "command:2", java.sql.Timestamp.from(Instant.parse("2026-09-27T01:02:00Z")));
        jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                run, "COMMAND_RESULT", "earlier", "command:1", java.sql.Timestamp.from(Instant.parse("2026-09-27T01:01:00Z")));

        var detail = service.detail(1L, run);
        assertThat(detail.outputs()).extracting(OperationRunQueryService.CommandOutput::sequenceNo).containsExactly(1, 2);
        assertThat(detail.outputs().get(0).stdout()).isEmpty();
        assertThat(detail.outputs().get(0).stderr()).isEmpty();
        assertThat(detail.evidence()).extracting(OperationRunQueryService.Evidence::content).containsExactly("earlier", "later");
    }

    @Test
    void hidesOtherUsersRunAsNotFound() {
        long run = insertRun("trace-private", 2, "docker.ps", "SUCCESS", "2026-09-27T01:00:00Z");
        assertThatThrownBy(() -> service.detail(1L, run))
                .isInstanceOf(BusinessException.class)
                .hasMessage("OPERATION_RUN_NOT_FOUND");
    }

    private long insertRun(String traceId, long userId, String toolId, String status, String startedAt) {
        jdbc.update("INSERT INTO operation_run_record(trace_id,user_id,session_id,runtime_id,tool_id,status,started_at,ended_at) VALUES(?,?,?,?,?,?,?,?)",
                traceId, userId, 10L, "runtime-1", toolId, status,
                java.sql.Timestamp.from(Instant.parse(startedAt)), java.sql.Timestamp.from(Instant.parse(startedAt).plusSeconds(5)));
        return jdbc.queryForObject("SELECT id FROM operation_run_record WHERE trace_id=?", Long.class, traceId);
    }

    private void insertOutput(long runId, int sequence, int exitCode, String stdout, String stderr) {
        jdbc.update("INSERT INTO operation_run_output(run_id,sequence_no,command_text,exit_code,stdout_text,stderr_text,started_at,ended_at) VALUES(?,?,?,?,?,?,?,?)",
                runId, sequence, "echo test", exitCode, stdout, stderr,
                java.sql.Timestamp.from(Instant.parse("2026-09-27T01:00:00Z")),
                java.sql.Timestamp.from(Instant.parse("2026-09-27T01:00:01Z")));
    }
}
