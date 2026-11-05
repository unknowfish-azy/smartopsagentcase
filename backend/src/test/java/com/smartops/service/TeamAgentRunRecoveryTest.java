package com.smartops.service;

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

/**
 * OPS-04：审批消费后中断的对账，不允许出现"授权已用、状态卡住"或自动重跑。
 */
class TeamAgentRunRecoveryTest {

    private static final long STALE_MS = 600_000L;

    private JdbcTemplate jdbc;
    private JdbcOperationRunRecorder recorder;
    private TeamAgentRunRecoveryScheduler scheduler;

    @BeforeEach
    void setUp() {
        DriverManagerDataSource source = new DriverManagerDataSource(
                "jdbc:h2:mem:team-run-recovery-" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        new ResourceDatabasePopulator(
                new ClassPathResource("schema.sql"),
                new ClassPathResource("db/migration/V20261003.2__team_agent_runs.sql"),
                new ClassPathResource("db/migration/V20261105.2__operation_run_governance.sql")
        ).execute(source);
        jdbc = new JdbcTemplate(source);
        recorder = new JdbcOperationRunRecorder(jdbc);
        scheduler = new TeamAgentRunRecoveryScheduler(jdbc, STALE_MS);
    }

    @Test
    @DisplayName("审批已消费、执行已完成但状态没写回：按 Run 事实回填为 SUCCEEDED")
    void reconcilesTeamRunFromSucceededOperationRun() {
        long teamRunId = teamRun("RUNNING", Instant.now().minusSeconds(900));
        operationRun(teamRunId, "SUCCEEDED");

        assertThat(scheduler.recoverOnce(Instant.now())).isEqualTo(1);

        assertThat(teamStatus(teamRunId)).isEqualTo("SUCCEEDED");
        assertThat(jdbc.queryForList(
                "SELECT evidence_type FROM operation_run_evidence WHERE evidence_type='TEAM_RUN_RECONCILED'", String.class))
                .hasSize(1);
    }

    @Test
    @DisplayName("授权已消费但找不到任何执行记录：置为 UNCERTAIN 等人工核验，不猜成失败")
    void grantConsumedWithoutExecutionBecomesUncertain() {
        long teamRunId = teamRun("RUNNING", Instant.now().minusSeconds(900));

        assertThat(scheduler.recoverOnce(Instant.now())).isEqualTo(1);

        assertThat(teamStatus(teamRunId)).isEqualTo("UNCERTAIN");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM operation_run_evidence", Integer.class)).isZero();
    }

    @Test
    @DisplayName("Run 结果为 UNCERTAIN 时团队运行同口径，不被改写成成功或失败")
    void uncertainOperationStaysUncertain() {
        long teamRunId = teamRun("RUNNING", Instant.now().minusSeconds(900));
        operationRun(teamRunId, "UNCERTAIN");

        scheduler.recoverOnce(Instant.now());

        assertThat(teamStatus(teamRunId)).isEqualTo("UNCERTAIN");
    }

    @Test
    @DisplayName("仍在执行的 Run 不被对账打断，未超时的团队运行也不动")
    void runningOperationAndFreshTeamRunAreLeftAlone() {
        long runningOpTeamRun = teamRun("RUNNING", Instant.now().minusSeconds(900));
        operationRun(runningOpTeamRun, "RUNNING");
        long freshTeamRun = teamRun("RUNNING", Instant.now().minusSeconds(30));

        assertThat(scheduler.recoverOnce(Instant.now())).isZero();

        assertThat(teamStatus(runningOpTeamRun)).isEqualTo("RUNNING");
        assertThat(teamStatus(freshTeamRun)).isEqualTo("RUNNING");
    }

    @Test
    @DisplayName("对账幂等：重复扫描不重复回填")
    void recoveryIsIdempotent() {
        long teamRunId = teamRun("RUNNING", Instant.now().minusSeconds(900));
        operationRun(teamRunId, "SUCCEEDED");

        assertThat(scheduler.recoverOnce(Instant.now())).isEqualTo(1);
        assertThat(scheduler.recoverOnce(Instant.now())).isZero();
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM operation_run_evidence WHERE evidence_type='TEAM_RUN_RECONCILED'",
                Integer.class)).isEqualTo(1);
    }

    private long teamRun(String status, Instant createdAt) {
        jdbc.update("INSERT INTO team_agent_run(team_id,agent_id,version_id,requester_id,runtime_id,tool_id,"
                        + "read_only,parameters_json,status,created_at) VALUES(1,1,1,7,'runtime-1','host-health',"
                        + "TRUE,'{}',?,?)",
                status, Timestamp.from(createdAt));
        return jdbc.queryForObject("SELECT MAX(id) FROM team_agent_run", Long.class);
    }

    private void operationRun(long teamRunId, String status) {
        OperationRunRecorder.RunSpec spec = new OperationRunRecorder.RunSpec(
                "trace-team-" + teamRunId, 7L, new TestRuntime("runtime-1"), "host-health",
                "tool-run:7:team-run-" + teamRunId, Instant.now().minusSeconds(800),
                Instant.now().minusSeconds(600), 1024, 60_000);
        OperationRunRecorder.RunHandle run = recorder.start(spec);
        if (!"RUNNING".equals(status)) recorder.finish(run, status, Instant.now());
    }

    private String teamStatus(long teamRunId) {
        return jdbc.queryForObject("SELECT status FROM team_agent_run WHERE id=?", String.class, teamRunId);
    }

    private record TestRuntime(String id) implements OperationRuntime {
        @Override public Long userId() { return 7L; }
        @Override public Long sessionId() { return null; }
        @Override public void write(String input) { }
        @Override public void resize(int columns, int rows) { }
        @Override public void onOutput(OutputListener listener) { }
        @Override public boolean isOpen() { return true; }
        @Override public void close() { }
    }
}
