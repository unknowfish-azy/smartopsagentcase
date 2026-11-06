package com.smartops.service;

import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * PERF-04：多机批量命令复用 Runbook 的 Run + 目标子任务模型。
 *
 * <p>用真实 Flyway/H2 与真实 operation_run_record 验证：有界并发、逐目标状态、
 * 失败/未知单列、取消后停止派发、输出截断标志。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:multi_exec_it;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        // H2 2.2.224 在并发插入 auto_increment 列时会偶发重复分配主键（已用最小用例复现），
        // 这是测试数据库的缺陷，生产 MySQL 不受影响。这里把连接池串行化，只保留执行层并发，
        // 避免把 H2 的 identity 缺陷误判为批量执行的问题；Flyway 使用独立连接，不受该限制。
        "spring.datasource.hikari.maximum-pool-size=1",
        "spring.flyway.url=jdbc:h2:mem:multi_exec_it;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "spring.flyway.user=sa",
        "spring.flyway.password=",
        "smartops.operations.ssh.max-per-user=500",
        "smartops.operations.ssh.max-per-session=4",
        "smartops.operations.ssh.sweep-initial-delay-ms=86400000",
        "smartops.operations.ssh.sweep-interval-ms=86400000",
        "smartops.operations.multi-exec.max-parallel=10",
        "smartops.operations.multi-exec.timeout-ms=120000",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.schedule.interval-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.runbook.alert.interval-ms=86400000"
})
class MultiExecBatchIntegrationTest {
    private static final long OWNER = 81L;

    @Autowired JdbcTemplate jdbc;
    @Autowired OperationRuntimeRegistry registry;
    @Autowired MultiExecService service;

    @BeforeEach
    void reset() {
        for (String table : List.of("runbook_run_target", "runbook_run", "runbook_step", "runbook_version",
                "runbook_schedule", "runbook_trigger", "runbook",
                "operation_run_output", "operation_run_evidence", "operation_run_record",
                "sentinel_notification", "sentinel_alert_event", "sentinel_metric_sample", "sentinel_alert",
                "sentinel_silence", "sentinel_alert_rule", "sentinel_task")) {
            jdbc.update("DELETE FROM " + table);
        }
    }

    @Test
    @DisplayName("100 目标、并发上限 10、10% 失败：单条 Run + 逐目标完整状态")
    void hundredTargetsWithBoundedConcurrency() {
        RuntimeMetrics metrics = new RuntimeMetrics();
        List<String> runtimeIds = new ArrayList<>();
        for (int index = 0; index < 100; index++) {
            String mode = index % 10 == 0 ? "fail" : "ok";
            runtimeIds.add(register(OWNER, 20_000L + index, mode, 20L, metrics));
        }

        MultiExecService.Preview preview = service.preview(OWNER, "uptime", runtimeIds, false);
        MultiExecService.ExecutionResult result = service.execute(OWNER, preview.id(),
                preview.confirmationNonce(), preview.confirmationNonce());

        assertThat(result.results()).hasSize(100);
        assertThat(result.succeeded()).isEqualTo(90);
        assertThat(result.failed()).isEqualTo(10);
        assertThat(result.unknown()).isZero();
        assertThat(result.status()).isEqualTo("PARTIAL");
        assertThat(metrics.maxActive.get()).isLessThanOrEqualTo(10);
        assertThat(metrics.executed.get()).isEqualTo(100);

        Integer runs = jdbc.queryForObject(
                "SELECT COUNT(*) FROM runbook_run WHERE user_id=? AND total_targets=100", Integer.class, OWNER);
        assertThat(runs).isEqualTo(1);
        long runId = result.runId();
        Integer targets = jdbc.queryForObject(
                "SELECT COUNT(*) FROM runbook_run_target WHERE run_id=? AND status IN ('SUCCEEDED','FAILED')",
                Integer.class, runId);
        assertThat(targets).isEqualTo(100);
        Integer withoutRun = jdbc.queryForObject(
                "SELECT COUNT(*) FROM runbook_run_target WHERE run_id=? AND operation_run_id IS NULL",
                Integer.class, runId);
        assertThat(withoutRun).isZero();
        Integer operationRuns = jdbc.queryForObject(
                "SELECT COUNT(*) FROM operation_run_record", Integer.class);
        assertThat(operationRuns).isEqualTo(100);
    }

    @Test
    @DisplayName("执行超时目标单列为 UNKNOWN，不自动重试")
    void uncertainTargetIsListedSeparately() {
        RuntimeMetrics metrics = new RuntimeMetrics();
        String ok = register(OWNER, 31_001L, "ok", 0L, metrics);
        String timeout = register(OWNER, 31_002L, "timeout", 0L, metrics);

        MultiExecService.Preview preview = service.preview(OWNER, "systemctl restart nginx", List.of(ok, timeout), false);
        MultiExecService.ExecutionResult result = service.execute(OWNER, preview.id(),
                preview.confirmationNonce(), preview.confirmationNonce());

        assertThat(result.results()).hasSize(2);
        assertThat(result.unknown()).isEqualTo(1);
        assertThat(result.unknownTargets()).containsExactly(timeout);
        assertThat(result.results()).anySatisfy(target -> {
            assertThat(target.runtimeId()).isEqualTo(timeout);
            assertThat(target.status()).isEqualTo("UNKNOWN");
        });
        Integer attempts = jdbc.queryForObject("""
                SELECT COUNT(*) FROM operation_run_record r
                  JOIN runbook_run_target t ON t.operation_run_id = r.id
                 WHERE t.run_id=? AND t.runtime_id=?
                """, Integer.class, result.runId(), timeout);
        assertThat(attempts).isEqualTo(1);
    }

    @Test
    @DisplayName("取消后停止派发：未开始的目标保持 CANCELLED/未派发")
    void cancelStopsFurtherDispatch() throws Exception {
        RuntimeMetrics metrics = new RuntimeMetrics();
        CountDownLatch firstStarted = new CountDownLatch(1);
        List<String> runtimeIds = new ArrayList<>();
        for (int index = 0; index < 100; index++) {
            runtimeIds.add(register(OWNER, 32_000L + index, "slow", 150L, metrics, firstStarted));
        }

        MultiExecService.Preview preview = service.preview(OWNER, "uptime", runtimeIds, false);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<MultiExecService.ExecutionResult> future =
                    CompletableFuture.supplyAsync(() -> service.execute(OWNER, preview.id(),
                            preview.confirmationNonce(), preview.confirmationNonce()), pool);
            assertThat(firstStarted.await(10, TimeUnit.SECONDS)).isTrue();
            MultiExecService.CancelResult cancel = service.cancel(OWNER, preview.id());
            assertThat(cancel.cancelled()).isTrue();
            assertThat(cancel.runId()).isEqualTo(future.get(60, TimeUnit.SECONDS).runId());

            MultiExecService.ExecutionResult result = future.get(60, TimeUnit.SECONDS);
            assertThat(metrics.executed.get()).isLessThan(100);
            assertThat(result.cancelled()).isGreaterThanOrEqualTo(90);
            assertThat(result.notDispatchedTargets()).hasSizeGreaterThanOrEqualTo(90);
            assertThat(result.results()).hasSize(100);
            assertThat(result.results()).anySatisfy(target -> {
                assertThat(target.status()).isEqualTo("CANCELLED");
                assertThat(target.dispatchStatus()).isNull();
            });
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    @DisplayName("命令输出超过预算时逐目标 Run 标记截断")
    void truncatedOutputIsRecorded() {
        RuntimeMetrics metrics = new RuntimeMetrics();
        String runtimeId = register(OWNER, 33_001L, "truncated", 0L, metrics);

        MultiExecService.Preview preview = service.preview(OWNER, "cat /var/log/huge.log", List.of(runtimeId), false);
        MultiExecService.ExecutionResult result = service.execute(OWNER, preview.id(),
                preview.confirmationNonce(), preview.confirmationNonce());

        assertThat(result.succeeded()).isEqualTo(1);
        Long operationRunId = jdbc.queryForObject(
                "SELECT operation_run_id FROM runbook_run_target WHERE run_id=? AND runtime_id=?",
                Long.class, result.runId(), runtimeId);
        assertThat(operationRunId).isNotNull();
        List<Integer> flags = jdbc.queryForList(
                "SELECT truncated FROM operation_run_output WHERE run_id=?", Integer.class, operationRunId);
        assertThat(flags).containsExactly(1);
    }

    private String register(long userId, long sessionId, String mode, long sleepMillis, RuntimeMetrics metrics) {
        return register(userId, sessionId, mode, sleepMillis, metrics, null);
    }

    private String register(long userId, long sessionId, String mode, long sleepMillis, RuntimeMetrics metrics,
                            CountDownLatch firstStarted) {
        return registry.register(new FakeRuntime(userId, sessionId, mode, sleepMillis, metrics, firstStarted));
    }

    static final class RuntimeMetrics {
        final AtomicInteger active = new AtomicInteger();
        final AtomicInteger maxActive = new AtomicInteger();
        final AtomicInteger executed = new AtomicInteger();
    }

    private static final class FakeRuntime implements OperationRuntime {
        private final Long userId;
        private final Long sessionId;
        private final String mode;
        private final long sleepMillis;
        private final RuntimeMetrics metrics;
        private final CountDownLatch firstStarted;
        private volatile boolean open = true;

        private FakeRuntime(Long userId, Long sessionId, String mode, long sleepMillis, RuntimeMetrics metrics,
                            CountDownLatch firstStarted) {
            this.userId = userId;
            this.sessionId = sessionId;
            this.mode = mode;
            this.sleepMillis = sleepMillis;
            this.metrics = metrics;
            this.firstStarted = firstStarted;
        }

        @Override public String id() { return "multi-" + sessionId; }
        @Override public Long userId() { return userId; }
        @Override public Long sessionId() { return sessionId; }
        @Override public void write(String input) throws IOException { }
        @Override public void resize(int columns, int rows) throws IOException { }
        @Override public void onOutput(OutputListener listener) { }
        @Override public boolean isOpen() { return open; }

        @Override
        public CommandResult execute(String command, long timeoutMillis) throws IOException {
            metrics.executed.incrementAndGet();
            int now = metrics.active.incrementAndGet();
            metrics.maxActive.accumulateAndGet(now, Math::max);
            try {
                if (firstStarted != null) firstStarted.countDown();
                if (sleepMillis > 0) Thread.sleep(sleepMillis);
                return switch (mode) {
                    case "fail" -> new CommandResult(1, "", "command failed");
                    case "timeout" -> throw new IOException("COMMAND_TIMEOUT");
                    case "truncated" -> new CommandResult(0, "ok", "", true);
                    default -> new CommandResult(0, "ok", "");
                };
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IOException("COMMAND_TIMEOUT");
            } finally {
                metrics.active.decrementAndGet();
            }
        }

        @Override public void close() { open = false; }
    }
}
