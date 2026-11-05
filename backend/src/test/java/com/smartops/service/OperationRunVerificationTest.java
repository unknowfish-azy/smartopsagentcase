package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-04 恢复闭环验证：UNCERTAIN 必须由人核验，不允许被当成普通失败直接重试。
 */
class OperationRunVerificationTest {

    private JdbcTemplate jdbc;
    private JdbcOperationRunRecorder recorder;
    private OperationRunQueryService query;

    @BeforeEach
    void setUp() {
        DriverManagerDataSource source = new DriverManagerDataSource(
                "jdbc:h2:mem:run-verify-" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        new ResourceDatabasePopulator(
                new ClassPathResource("schema.sql"),
                new ClassPathResource("db/migration/V20261105.2__operation_run_governance.sql")
        ).execute(source);
        jdbc = new JdbcTemplate(source);
        recorder = new JdbcOperationRunRecorder(jdbc);
        query = new OperationRunQueryService(jdbc);
    }

    @Test
    @DisplayName("核验 DONE：UNCERTAIN 落为 VERIFIED_SUCCEEDED，并把人工依据写入证据")
    void verifyingDoneClosesTheRunWithEvidence() {
        long runId = uncertainRun(7L);

        query.verify(7L, runId, "DONE", "已在远端确认服务已重启且端口监听恢复");

        assertThat(jdbc.queryForObject("SELECT status FROM operation_run_record WHERE id=?", String.class, runId))
                .isEqualTo("VERIFIED_SUCCEEDED");
        assertThat(jdbc.queryForList("SELECT content FROM operation_run_evidence WHERE run_id=? AND evidence_type='RUN_VERIFIED'",
                String.class, runId))
                .singleElement()
                .asString()
                .contains("DONE")
                .contains("已在远端确认服务已重启");
    }

    @Test
    @DisplayName("核验 NOT_DONE：落为 VERIFIED_FAILED，与未核实的 UNCERTAIN 区分")
    void verifyingNotDoneDistinguishesFromPlainFailure() {
        long runId = uncertainRun(7L);

        query.verify(7L, runId, "NOT_DONE", "远端未产生变更记录，可重新发起");

        assertThat(jdbc.queryForObject("SELECT status FROM operation_run_record WHERE id=?", String.class, runId))
                .isEqualTo("VERIFIED_FAILED");
    }

    @Test
    @DisplayName("非 UNCERTAIN 不能核验，也不能绕过人工核验直接改结论")
    void onlyUncertainRunsCanBeVerified() {
        OperationRunRecorder.RunHandle run = recorder.start("trace-ok", 7L,
                new TestRuntime("runtime-1", 7L, null), "host-health", Instant.now());
        recorder.finish(run, "SUCCEEDED", Instant.now());

        assertThatThrownBy(() -> query.verify(7L, run.id(), "DONE", "确认成功"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("OPERATION_RUN_NOT_UNCERTAIN");

        // 已核验过的也不能被二次改写结论
        long runId = uncertainRun(7L);
        query.verify(7L, runId, "DONE", "已确认");
        assertThatThrownBy(() -> query.verify(7L, runId, "NOT_DONE", "改口"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("OPERATION_RUN_NOT_UNCERTAIN");
    }

    @Test
    @DisplayName("核验必须给依据，且只能核验自己的运行")
    void verificationRequiresEvidenceAndOwnership() {
        long runId = uncertainRun(7L);

        assertThatThrownBy(() -> query.verify(7L, runId, "DONE", " "))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("OPERATION_RUN_VERIFY_NOTE_REQUIRED");
        assertThatThrownBy(() -> query.verify(7L, runId, "MAYBE", "猜测"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("OPERATION_RUN_VERIFY_DECISION_INVALID");
        assertThatThrownBy(() -> query.verify(9L, runId, "DONE", "别人的运行"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("OPERATION_RUN_NOT_FOUND");
        assertThatThrownBy(() -> query.verify(7L, 999L, "DONE", "不存在的运行"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("OPERATION_RUN_NOT_FOUND");
    }

    @Test
    @DisplayName("恢复扫描幂等：重复扫描不会重复改判或重复写证据")
    void recoveryScanIsIdempotent() {
        Instant startedAt = Instant.now();
        OperationRunRecorder.RunHandle run = recorder.start("trace-stale", 7L,
                new TestRuntime("runtime-1", 7L, null), "service-restart", startedAt);
        // 心跳停在很久之前，模拟执行进程消失
        jdbc.update("UPDATE operation_run_record SET heartbeat_at=?, lease_expires_at=? WHERE id=?",
                Timestamp.from(startedAt), Timestamp.from(startedAt.plusSeconds(30)), run.id());

        OperationRunRecoveryScheduler scheduler = new OperationRunRecoveryScheduler(jdbc, 90_000L);
        assertThat(scheduler.recoverOnce(startedAt.plusSeconds(600))).isEqualTo(1);
        assertThat(scheduler.recoverOnce(startedAt.plusSeconds(601))).isZero();
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM operation_run_evidence WHERE run_id=? AND evidence_type='RUN_STALE'",
                Integer.class, run.id())).isEqualTo(1);
    }

    /** 直接构造一条"进程消失后遗留"的 UNCERTAIN 运行。 */
    private long uncertainRun(long userId) {
        OperationRunRecorder.RunHandle run = recorder.start("trace-uncertain-" + UUID.randomUUID(), userId,
                new TestRuntime("runtime-1", userId, null), "service-restart", Instant.now());
        jdbc.update("UPDATE operation_run_record SET status='UNCERTAIN', ended_at=? WHERE id=?",
                Timestamp.from(Instant.now()), run.id());
        return run.id();
    }

    private record TestRuntime(String id, Long userId, Long sessionId) implements OperationRuntime {
        @Override public void write(String input) { }
        @Override public void resize(int columns, int rows) { }
        @Override public void onOutput(OutputListener listener) { }
        @Override public boolean isOpen() { return true; }
        @Override public void close() { }
    }
}
