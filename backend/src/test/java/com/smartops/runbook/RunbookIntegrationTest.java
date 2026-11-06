package com.smartops.runbook;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import com.smartops.runbook.RunbookCatalogService.ParameterSpec;
import com.smartops.runbook.RunbookCatalogService.StepSpec;
import com.smartops.runbook.RunbookCatalogService.VersionDraft;
import com.smartops.runbook.RunbookExecutionService.PlanResult;
import com.smartops.runbook.RunbookExecutionService.RunView;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * P0-04 Runbook 与自动化作业的集成验证。
 *
 * <p>覆盖清单里的每一条验收：审批快照与实际执行一致、前置/执行/后置/回滚步骤、
 * 批次与金丝雀、参数 Schema、超时/失败/未知分开、每目标结果、定时与事件触发。</p>
 *
 * <p>用真实 Flyway 迁移 + 真实 operation_run_record：Runbook 的价值在于
 * "谁在什么版本、用什么参数、对哪些目标做了什么"可被逐条核验，
 * 用替身验证会把最容易出错的 SQL 与状态映射放过去。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:runbook_it;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        // 运行通道注册表按用户/会话设配额（生产默认 20/4）；本测试的假连接都把 session 记为 7，
        // 且注册表是单例不会随用例清空，因此这里放宽配额，只验证编排语义。
        "smartops.operations.ssh.max-per-user=500",
        "smartops.operations.ssh.max-per-session=500",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.schedule.interval-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.runbook.alert.interval-ms=86400000"
})
class RunbookIntegrationTest {

    private static final long OWNER = 91L;
    private static final long APPROVER = 92L;
    private static final long SECOND_APPROVER = 93L;
    private static final long STRANGER = 94L;

    @Autowired JdbcTemplate jdbc;
    @Autowired RunbookCatalogService catalog;
    @Autowired RunbookExecutionService execution;
    @Autowired OperationRuntimeRegistry registry;

    private final Map<String, FakeRuntime> runtimes = new LinkedHashMap<>();

    @BeforeEach
    void reset() {
        for (String table : List.of("runbook_run_target", "runbook_run", "runbook_step", "runbook_version",
                "runbook_schedule", "runbook_trigger", "runbook",
                "operation_run_output", "operation_run_evidence", "operation_run_record",
                "sentinel_notification", "sentinel_alert_event", "sentinel_metric_sample", "sentinel_alert",
                "sentinel_silence", "sentinel_alert_rule", "sentinel_task")) {
            jdbc.update("DELETE FROM " + table);
        }
        runtimes.clear();
    }

    /* ── 审批快照与执行一致 ───────────────────────────────────────────── */

    @Test
    @DisplayName("计划固定版本/参数/目标；审批后才能带确认码执行，且实际执行内容与批准一致")
    void approvedSnapshotIsWhatRuns() {
        long runbookId = catalog.create(OWNER, "prod-deploy", "生产部署", "PROD", "HIGH", OWNER).id();
        saveAndPublish(runbookId, List.of(
                new ParameterSpec("service", "STRING", true, "api", null, "服务名")),
                List.of(
                        new StepSpec("PRE_CHECK", 1, "pre", "echo ${service}", 0, "ABORT", null),
                        new StepSpec("EXECUTE", 1, "deploy", "deploy ${service}", 0, "ABORT", null),
                        new StepSpec("POST_CHECK", 1, "post", "echo ${service}", 0, "ABORT", null),
                        new StepSpec("ROLLBACK", 1, "rollback", "rollback ${service}", 0, "CONTINUE", null)));

        String first = register(OWNER, "ok");
        String second = register(OWNER, "ok");
        String strangerRuntime = register(STRANGER, "ok");

        assertThatThrownBy(() -> execution.plan(OWNER, runbookId, List.of(first), Map.of("nope", "x"), false))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_PARAMETER_UNKNOWN");
        assertThatThrownBy(() -> execution.plan(OWNER, runbookId, List.of(strangerRuntime), Map.of(), false))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNTIME_NOT_FOUND");
        assertThatThrownBy(() -> execution.plan(OWNER, runbookId, List.of(), Map.of(), false))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_TARGETS_REQUIRED");

        PlanResult plan = execution.plan(OWNER, runbookId, List.of(first, second), Map.of(), false);
        assertThat(plan.status()).isEqualTo("PENDING_APPROVAL");
        assertThat(plan.requiredApprovals()).isGreaterThanOrEqualTo(1);
        assertThat(plan.confirmationNonce()).isNotBlank();
        assertThat(plan.steps()).anySatisfy(step ->
                assertThat(step.command()).isEqualTo("deploy api"));

        assertThatThrownBy(() -> execution.approve(OWNER, plan.runId(), "自批"))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_SELF_APPROVAL_FORBIDDEN");

        approveIfNeeded(plan);
        assertThat(execution.detail(OWNER, plan.runId()).status()).isEqualTo("APPROVED");

        assertThatThrownBy(() -> execution.execute(OWNER, plan.runId(), "wrong-nonce"))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_CONFIRMATION_REQUIRED");

        RunView done = execution.execute(OWNER, plan.runId(), plan.confirmationNonce());
        assertThat(done.status()).isEqualTo("SUCCEEDED");
        assertThat(done.totalTargets()).isEqualTo(2);
        assertThat(done.succeeded()).isEqualTo(2);
        assertThat(done.targets()).allSatisfy(target -> {
            assertThat(target.status()).isEqualTo("SUCCEEDED");
            // SENT / 执行阶段结束 / 后置验证通过各留独立证据，不只靠最终状态反推。
            assertThat(target.dispatchStatus()).isEqualTo("SENT");
            assertThat(target.dispatchedAt()).isNotNull();
            assertThat(target.executedAt()).isNotNull();
            assertThat(target.verifiedAt()).isNotNull();
        });

        Integer runs = jdbc.queryForObject("SELECT COUNT(*) FROM operation_run_record WHERE tool_id=?",
                Integer.class, "runbook:" + runbookId);
        assertThat(runs).isEqualTo(2);
        assertThat(runtimes.get(first).commands).containsExactly("echo api", "deploy api", "echo api");

        assertThatThrownBy(() -> execution.execute(OWNER, plan.runId(), plan.confirmationNonce()))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_RUN_NOT_APPROVED");
    }

    /* ── 部分成功 / 失败 / 未知分开 ─────────────────────────────────── */

    @Test
    @DisplayName("目标结果逐条记录：成功、失败、未知不合并；未知不自动重试")
    void partialFailureAndUnknownStaySeparate() {
        long runbookId = catalog.create(OWNER, "rolling-restart", "滚动重启", "DEV", "LOW", OWNER).id();
        saveAndPublish(runbookId, List.of(), List.of(
                new StepSpec("EXECUTE", 1, "restart", "restart service", 0, "ABORT", null)));

        String ok = register(OWNER, "ok");
        String fail = register(OWNER, "fail");
        String unknown = register(OWNER, "timeout");

        PlanResult plan = execution.plan(OWNER, runbookId, List.of(ok, fail, unknown), Map.of(), false);
        approveIfNeeded(plan);
        RunView done = execution.execute(OWNER, plan.runId(), plan.confirmationNonce());

        assertThat(done.status()).isEqualTo("UNKNOWN");
        assertThat(done.succeeded()).isEqualTo(1);
        assertThat(done.failed()).isEqualTo(1);
        assertThat(done.unknown()).isEqualTo(1);
        assertThat(statusOf(done, ok)).isEqualTo("SUCCEEDED");
        assertThat(statusOf(done, fail)).isEqualTo("FAILED");
        assertThat(statusOf(done, unknown)).isEqualTo("UNKNOWN");

        List<String> runStatuses = jdbc.queryForList(
                "SELECT status FROM operation_run_record WHERE tool_id=? ORDER BY id", String.class,
                "runbook:" + runbookId);
        assertThat(runStatuses).containsExactlyInAnyOrder("SUCCEEDED", "FAILED", "UNCERTAIN");
        // 未知的目标没有被自动重跑：每个目标只有一条 Run。
        assertThat(runStatuses).hasSize(3);
    }

    @Test
    @DisplayName("金丝雀失败时不放量，其余目标如实标记跳过")
    void canaryFailureStopsRemainingBatches() {
        long runbookId = catalog.create(OWNER, "canary-job", "金丝雀", "DEV", "LOW", OWNER).id();
        saveAndPublish(runbookId, List.of(), List.of(
                        new StepSpec("EXECUTE", 1, "run", "run job", 0, "ABORT", null)),
                30, 0, 2, 1, 1);

        String canary = register(OWNER, "fail");
        String nextOne = register(OWNER, "ok");
        String nextTwo = register(OWNER, "ok");

        PlanResult plan = execution.plan(OWNER, runbookId, List.of(canary, nextOne, nextTwo), Map.of(), false);
        approveIfNeeded(plan);
        RunView done = execution.execute(OWNER, plan.runId(), plan.confirmationNonce());

        assertThat(done.status()).isEqualTo("FAILED");
        assertThat(statusOf(done, canary)).isEqualTo("FAILED");
        assertThat(statusOf(done, nextOne)).isEqualTo("SKIPPED");
        assertThat(statusOf(done, nextTwo)).isEqualTo("SKIPPED");
        assertThat(done.targets()).filteredOn(target -> target.status().equals("SKIPPED"))
                .allSatisfy(target -> {
                    assertThat(target.dispatchStatus()).isNull();
                    assertThat(target.dispatchedAt()).isNull();
                    assertThat(target.executedAt()).isNull();
                    assertThat(target.verifiedAt()).isNull();
                });
        assertThat(runtimes.get(nextOne).commands).isEmpty();
        assertThat(runtimes.get(nextTwo).commands).isEmpty();
    }

    /* ── 回滚与失败分支 ─────────────────────────────────────────────── */

    @Test
    @DisplayName("执行失败按 ROLLBACK 分支回滚；未知结果可人工回滚")
    void rollbackBranchAndManualRollback() {
        long autoRollback = catalog.create(OWNER, "auto-rollback", "失败即回滚", "DEV", "LOW", OWNER).id();
        saveAndPublish(autoRollback, List.of(), List.of(
                new StepSpec("EXECUTE", 1, "apply", "apply change", 0, "ROLLBACK", null),
                new StepSpec("ROLLBACK", 1, "undo", "rollback change", 0, "CONTINUE", null)));

        String failing = register(OWNER, "fail");
        PlanResult plan = execution.plan(OWNER, autoRollback, List.of(failing), Map.of(), false);
        approveIfNeeded(plan);
        RunView done = execution.execute(OWNER, plan.runId(), plan.confirmationNonce());

        assertThat(done.status()).isEqualTo("FAILED");
        assertThat(statusOf(done, failing)).isEqualTo("ROLLED_BACK");
        var target = done.targets().get(0);
        assertThat(target.rollbackStatus()).isEqualTo("ROLLED_BACK");
        assertThat(runtimes.get(failing).commands).containsExactly("apply change", "rollback change");

        long manual = catalog.create(OWNER, "manual-rollback", "未知后人工回滚", "DEV", "LOW", OWNER).id();
        saveAndPublish(manual, List.of(), List.of(
                new StepSpec("EXECUTE", 1, "apply", "apply change", 0, "ABORT", null),
                new StepSpec("ROLLBACK", 1, "undo", "rollback change", 0, "CONTINUE", null)));

        String uncertain = register(OWNER, "timeout");
        PlanResult unknownPlan = execution.plan(OWNER, manual, List.of(uncertain), Map.of(), false);
        approveIfNeeded(unknownPlan);
        RunView unknownRun = execution.execute(OWNER, unknownPlan.runId(), unknownPlan.confirmationNonce());
        assertThat(unknownRun.status()).isEqualTo("UNKNOWN");

        RunView rolledBack = execution.rollback(OWNER, unknownPlan.runId());
        assertThat(rolledBack.status()).isEqualTo("ROLLED_BACK");
        assertThat(statusOf(rolledBack, uncertain)).isEqualTo("ROLLED_BACK");
        assertThat(rolledBack.targets().get(0).rollbackStatus()).isEqualTo("ROLLED_BACK");
    }

    /* ── 审批内容一致性 ─────────────────────────────────────────────── */

    @Test
    @DisplayName("版本内容被改动后执行被拒绝（批准的与执行的不允许漂移）")
    void contentDriftIsRejected() {
        long runbookId = catalog.create(OWNER, "drift-job", "内容校验", "DEV", "LOW", OWNER).id();
        long versionId = saveAndPublish(runbookId, List.of(), List.of(
                new StepSpec("EXECUTE", 1, "run", "echo stable", 0, "ABORT", null)));

        String runtime = register(OWNER, "ok");
        PlanResult plan = execution.plan(OWNER, runbookId, List.of(runtime), Map.of(), false);
        approveIfNeeded(plan);

        jdbc.update("UPDATE runbook_step SET body='echo drifted' WHERE version_id=? AND phase='EXECUTE'", versionId);
        assertThatThrownBy(() -> execution.execute(OWNER, plan.runId(), plan.confirmationNonce()))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_CONTENT_DRIFT");
        assertThat(runtimes.get(runtime).commands).isEmpty();
    }

    /* ── 参数 Schema ────────────────────────────────────────────────── */

    @Test
    @DisplayName("必填参数缺失、类型不符、正则不符都在计划阶段拒绝")
    void parameterSchemaIsEnforced() {
        long runbookId = catalog.create(OWNER, "schema-job", "参数校验", "DEV", "LOW", OWNER).id();
        saveAndPublish(runbookId, List.of(
                new ParameterSpec("count", "NUMBER", true, null, null, "实例数"),
                new ParameterSpec("env", "STRING", false, "prod", "^[a-z]+$", "环境")),
                List.of(new StepSpec("EXECUTE", 1, "run", "run ${count} ${env}", 0, "ABORT", null)));
        String runtime = register(OWNER, "ok");

        assertThatThrownBy(() -> execution.plan(OWNER, runbookId, List.of(runtime), Map.of("env", "dev"), false))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_PARAMETER_MISSING:count");
        assertThatThrownBy(() -> execution.plan(OWNER, runbookId, List.of(runtime),
                Map.of("count", "abc", "env", "dev"), false))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_PARAMETER_TYPE_MISMATCH:count");
        assertThatThrownBy(() -> execution.plan(OWNER, runbookId, List.of(runtime),
                Map.of("count", "2", "env", "DEV"), false))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_PARAMETER_PATTERN_MISMATCH:env");
    }

    /* ── 定时与事件触发 ─────────────────────────────────────────────── */

    @Test
    @DisplayName("定时/告警触发只生成待绑定目标的作业，且同一触发幂等")
    void scheduleAndAlertTriggersCreateAwaitingRunsExactlyOnce() {
        long runbookId = catalog.create(OWNER, "nightly-check", "夜间巡检", "DEV", "LOW", OWNER).id();
        saveAndPublish(runbookId, List.of(), List.of(
                new StepSpec("EXECUTE", 1, "check", "check service", 0, "ABORT", null)));

        var schedule = execution.createSchedule(OWNER, runbookId, "0 2 * * *", "DEV", Instant.now().minusSeconds(60));
        assertThat(execution.fireDueSchedules()).isEqualTo(1);
        assertThat(execution.fireDueSchedules()).isEqualTo(0);
        assertThat(execution.listRuns(OWNER, "AWAITING_TARGETS", 10)).hasSize(1);
        assertThat(execution.listRuns(OWNER, "AWAITING_TARGETS", 10).get(0).trigger()).isEqualTo("SCHEDULE");

        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled) "
                + "VALUES(901,?, 'nightly', 'system', 'memory', 60, 1)", OWNER);
        jdbc.update("""
                INSERT INTO sentinel_alert(id,task_id,severity,status,title,metric,observed_value,threshold_value,fired_at)
                VALUES(902,901,'P0','OPEN','夜间巡检告警','memory','95.0','memory > 90',CURRENT_TIMESTAMP)
                """);
        execution.bindAlertTrigger(OWNER, runbookId, "P2");
        assertThat(execution.fireAlertTriggers(30, 100)).isEqualTo(1);
        assertThat(execution.fireAlertTriggers(30, 100)).isEqualTo(0);
        assertThat(execution.listRuns(OWNER, "AWAITING_TARGETS", 10)).hasSize(2);

        String runtime = register(OWNER, "ok");
        RunView awaiting = execution.listRuns(OWNER, "AWAITING_TARGETS", 10).get(0);
        PlanResult attached = execution.attachTargets(OWNER, awaiting.id(), List.of(runtime), Map.of(), false);
        approveIfNeeded(attached);
        RunView done = execution.execute(OWNER, awaiting.id(), attached.confirmationNonce());
        assertThat(done.status()).isEqualTo("SUCCEEDED");
        assertThat(done.trigger()).isIn("SCHEDULE", "ALERT");

        assertThat(schedule.enabled()).isTrue();
        assertThat(execution.listSchedules(OWNER).get(0).enabled()).isFalse();
    }

    /* ── 取消 ───────────────────────────────────────────────────────── */

    @Test
    @DisplayName("未执行的作业可以取消，终态不可再取消")
    void pendingRunCanBeCancelled() {
        long runbookId = catalog.create(OWNER, "cancel-job", "取消", "PROD", "HIGH", OWNER).id();
        saveAndPublish(runbookId, List.of(), List.of(
                new StepSpec("EXECUTE", 1, "run", "run job", 0, "ABORT", null)));
        String runtime = register(OWNER, "ok");

        PlanResult plan = execution.plan(OWNER, runbookId, List.of(runtime), Map.of(), true);
        assertThat(plan.status()).isEqualTo("PENDING_APPROVAL");
        RunView cancelled = execution.cancel(OWNER, plan.runId());
        assertThat(cancelled.status()).isEqualTo("CANCELLED");
        assertThat(cancelled.targets()).allSatisfy(target -> assertThat(target.status()).isEqualTo("CANCELLED"));

        assertThatThrownBy(() -> execution.cancel(OWNER, plan.runId()))
                .isInstanceOf(BusinessException.class).hasMessageContaining("RUNBOOK_RUN_NOT_CANCELLABLE");
    }

    /* ── 辅助 ───────────────────────────────────────────────────────── */

    private void approveIfNeeded(PlanResult plan) {
        if (!"PENDING_APPROVAL".equals(plan.status())) return;
        long[] approvers = {APPROVER, SECOND_APPROVER};
        for (int index = 0; index < plan.requiredApprovals(); index++) {
            execution.approve(approvers[Math.min(index, approvers.length - 1)], plan.runId(), "同意执行");
        }
    }

    private String statusOf(RunView run, String runtimeId) {
        return run.targets().stream().filter(target -> target.runtimeId().equals(runtimeId))
                .findFirst().map(RunbookExecutionService.TargetView::status)
                .orElseThrow(() -> new AssertionError("target not found: " + runtimeId));
    }

    private long saveAndPublish(long runbookId, List<ParameterSpec> parameters, List<StepSpec> steps) {
        return saveAndPublish(runbookId, parameters, steps, 60, 0, 2, 10, 0);
    }

    private long saveAndPublish(long runbookId, List<ParameterSpec> parameters, List<StepSpec> steps,
                                int timeoutSec, int retryLimit, int concurrency, int batchSize, int canarySize) {
        var version = catalog.saveVersion(OWNER, runbookId, new VersionDraft("v1", parameters, List.of(), "手工指定目标",
                timeoutSec, retryLimit, concurrency, batchSize, canarySize, null, steps));
        catalog.publish(OWNER, runbookId);
        return version.id();
    }

    private String register(long userId, String mode) {
        FakeRuntime runtime = new FakeRuntime("rt-" + UUID.randomUUID(), userId, mode);
        String id = registry.register(runtime);
        runtimes.put(id, runtime);
        return id;
    }

    /** 可控的假运行连接：只用于验证编排与状态映射，不模拟 SSH。 */
    private static final class FakeRuntime implements OperationRuntime {
        private final String id;
        private final Long userId;
        private final String mode;
        private final List<String> commands = new ArrayList<>();
        private volatile boolean open = true;

        FakeRuntime(String id, Long userId, String mode) {
            this.id = id;
            this.userId = userId;
            this.mode = mode;
        }

        @Override public String id() { return id; }
        @Override public Long userId() { return userId; }
        @Override public Long sessionId() { return 7L; }
        @Override public void write(String input) { commands.add(input); }
        @Override public void resize(int columns, int rows) { }
        @Override public void onOutput(OutputListener listener) { }
        @Override public boolean isOpen() { return open; }

        @Override
        public CommandResult execute(String command, long timeoutMillis) throws IOException {
            commands.add(command);
            if (command.startsWith("rollback")) return new CommandResult(0, "rolled back", "");
            return switch (mode) {
                case "fail" -> new CommandResult(1, "", "command failed");
                case "timeout" -> throw new IOException("COMMAND_TIMEOUT");
                default -> new CommandResult(0, "ok", "");
            };
        }

        @Override public void close() { open = false; }
    }
}
