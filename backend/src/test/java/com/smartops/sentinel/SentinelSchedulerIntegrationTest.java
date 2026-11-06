package com.smartops.sentinel;

import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.io.IOException;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * PERF-01 的集成验证：有界并发、背压、慢车道、队列年龄/到期延迟、失败下次时间、双副本互斥。
 *
 * <p>用真实 H2 + Flyway 迁移跑调度 SQL（认领是条件 UPDATE，替身测不出竞态）。
 * 采集用 {@link SlowRuntime} 真实耗时（150ms）而不是伪造统计值：这样才能观察到
 * "槽位占满即停止认领"的背压与"慢目标只占独立车道"的隔离效果。</p>
 *
 * <p>双副本用两个实例 ID 在同一 JVM 内并发轮询模拟；这不是 30 分钟连续压测，
 * 执行记录里会如实标注这一限制。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:sentinel_scheduler;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000",
        "smartops.sentinel.recovery.initial-delay-ms=86400000",
        "smartops.sentinel.dead-letter.initial-delay-ms=86400000",
        "smartops.sentinel.poll.max-concurrency=8",
        "smartops.sentinel.poll.batch-size=200",
        "smartops.sentinel.poll.lease-ms=20000",
        "smartops.sentinel.poll.slow-threshold-ms=2000",
        "smartops.sentinel.poll.slow-lane-size=2",
        "smartops.sentinel.poll.round-deadline-ms=20000"
})
class SentinelSchedulerIntegrationTest {

    private static final long OWNER_ID = 91L;
    private static final int BATCH = 200;
    private static final int MAX_CONCURRENCY = 8;
    private static final int SLOW_LANE = 2;

    @Autowired JdbcTemplate jdbc;
    @Autowired SentinelService sentinel;
    @Autowired OperationRuntimeRegistry runtimes;
    @Autowired com.smartops.service.OperationConnectionService connections;
    @Autowired @Qualifier("mfaClock") Clock clock;
    @Autowired SentinelAdvisor advisor;
    @Autowired com.smartops.service.TeamNotificationService notifications;
    @Autowired SentinelNotifier notifier;

    private final List<SentinelService> extraSchedulers = new ArrayList<>();
    private String runtimeId;

    @BeforeEach
    void reset() {
        stopExtraSchedulers();
        for (String table : List.of("sentinel_notification", "sentinel_alert_event", "sentinel_metric_sample",
                "sentinel_alert", "sentinel_silence", "sentinel_alert_rule", "sentinel_task",
                "sentinel_threshold_template")) {
            jdbc.update("DELETE FROM " + table);
        }
        jdbc.update("DELETE FROM app_user");
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role,enabled) VALUES(?,?,?,'operator',TRUE)",
                OWNER_ID, "scheduler-owner", "x");
        runtimeId = runtimes.register(new SlowRuntime(OWNER_ID));
    }

    @AfterEach
    void tearDown() {
        stopExtraSchedulers();
        if (runtimeId != null) {
            runtimes.removeOwned(runtimeId, OWNER_ID);
            runtimeId = null;
        }
    }

    @Test
    @DisplayName("1,000 个任务 / 5% 慢目标：背压有界、慢目标独立车道、队列年龄与到期延迟可观测")
    void boundedBackpressureIsolatesSlowTargets() {
        Instant now = clock.instant();
        seedTasks(1_000, now, 50);
        SentinelService scheduler = scheduler("perf-01-primary");
        assertThat(scheduler.schedulerConfig())
                .containsEntry("maxConcurrency", MAX_CONCURRENCY)
                .containsEntry("slowLaneSize", SLOW_LANE)
                .containsEntry("batchSize", BATCH);

        int claimed = scheduler.pollDueTasks();
        SentinelService.SchedulerStats stats = scheduler.schedulerStats();

        assertThat(stats.due()).isEqualTo(BATCH);
        // 通用槽位与慢车道各占满后立即停止认领，不会把 200 个到期任务一次性塞进队列。
        assertThat(stats.claimed()).isEqualTo(MAX_CONCURRENCY + SLOW_LANE);
        assertThat(claimed).isEqualTo(stats.claimed());
        assertThat(stats.claimedSlow()).isEqualTo(SLOW_LANE);
        assertThat(stats.deferredSlow()).isEqualTo(50 - SLOW_LANE);
        assertThat(stats.deferredByBackpressure()).isEqualTo(BATCH - stats.claimed() - stats.deferredSlow());
        // 到期时间在 5 分钟前，队列年龄与到期延迟必须是实测的非零值。
        assertThat(stats.queueAgeMs()).isGreaterThanOrEqualTo(290_000L);
        assertThat(stats.dueLatencyMs()).isGreaterThanOrEqualTo(stats.queueAgeMs() - 1_000L);

        // 第二轮继续认领被推迟的任务，证明"推迟"不是"丢弃"；本轮仍有大量到期任务。
        int secondRound = scheduler.pollDueTasks();
        assertThat(secondRound).isPositive();
        assertThat(scheduler.schedulerStats().due()).isEqualTo(BATCH);
    }

    @Test
    @DisplayName("两个副本并发轮询：同一任务不会被重复采集，租约与到期时间各自推进")
    void twoReplicasNeverClaimTheSameTask() throws Exception {
        Instant now = clock.instant();
        seedTasks(50, now, 0);
        SentinelService replicaA = scheduler("perf-01-replica-a");
        SentinelService replicaB = scheduler("perf-01-replica-b");

        for (int round = 0; round < 12 && attemptTotal() < 50; round++) {
            CountDownLatch start = new CountDownLatch(1);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            pool.submit(() -> {
                start.await();
                replicaA.pollDueTasks();
                return null;
            });
            pool.submit(() -> {
                start.await();
                replicaB.pollDueTasks();
                return null;
            });
            start.countDown();
            pool.shutdown();
            assertThat(pool.awaitTermination(30, TimeUnit.SECONDS)).isTrue();
        }

        // 每个任务恰好被采集一次：失败计数之和等于任务数，且没有任何任务 > 1。
        assertThat(attemptTotal()).isEqualTo(50);
        assertThat(jdbc.queryForObject(
                "SELECT MAX(success_count + failure_count) FROM sentinel_task", Integer.class)).isEqualTo(1);
    }

    @Test
    @DisplayName("失败任务写入指数退避后的下次采集时间与实测耗时，下一轮不会重采")
    void failureGetsExplicitNextRunTime() {
        Instant now = clock.instant();
        // 不绑定运行连接：采样会如实标记 no_runtime，并落入退避时间。
        jdbc.update("""
                INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled,next_run_at)
                VALUES(?,?,?,'system','memory',60,1,?)
                """, 7001L, OWNER_ID, "no-runtime", Timestamp.from(now.minusSeconds(120)));

        SentinelService scheduler = scheduler("perf-01-failure");
        assertThat(scheduler.pollDueTasks()).isEqualTo(1);

        Map<String, Object> row = jdbc.queryForMap(
                "SELECT last_status,consecutive_failures,next_run_at,last_duration_ms FROM sentinel_task WHERE id=?",
                7001L);
        assertThat(row.get("last_status")).isEqualTo("no_runtime");
        assertThat(((Number) row.get("consecutive_failures")).intValue()).isEqualTo(1);
        assertThat(((Timestamp) row.get("next_run_at")).toInstant()).isAfter(now);
        assertThat(row.get("last_duration_ms")).isNotNull();

        // 退避时间未到：下一轮不会再采集这个任务。
        assertThat(scheduler.pollDueTasks()).isZero();
    }

    /* ── 夹具 ─────────────────────────────────────────────────────────── */

    /**
     * 插入指定数量的到期任务：slowCount 个带 9s 实测耗时（进入慢车道），
     * 它们排在队首（next_run_at 更早），因此首轮就能看到慢车道被占满的效果。
     */
    private void seedTasks(int total, Instant now, int slowCount) {
        List<Object[]> batch = new ArrayList<>(total);
        for (int index = 0; index < total; index++) {
            boolean slow = index < slowCount;
            batch.add(new Object[]{
                    1000L + index, OWNER_ID, "task-" + index,
                    Timestamp.from(now.minusSeconds(slow ? 400 : 300)),
                    Timestamp.from(now.minusSeconds(300)),
                    slow ? 9_000 : null, runtimeId
            });
        }
        jdbc.batchUpdate("""
                INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled,
                                          next_run_at,last_seen_at,last_duration_ms,runtime_id)
                VALUES(?,?,?,'system','memory',60,1,?,?,?,?)
                """, batch);
    }

    private SentinelService scheduler(String instanceId) {
        SentinelService service = new SentinelService(jdbc, runtimes, connections, clock, advisor, notifications,
                notifier, MAX_CONCURRENCY, BATCH, 20_000L, 3_600L, 2_000L, SLOW_LANE, 20_000L, instanceId);
        extraSchedulers.add(service);
        return service;
    }

    private void stopExtraSchedulers() {
        extraSchedulers.forEach(SentinelService::shutdownWorkers);
        extraSchedulers.clear();
    }

    private int attemptTotal() {
        Integer total = jdbc.queryForObject(
                "SELECT COALESCE(SUM(success_count + failure_count),0) FROM sentinel_task", Integer.class);
        return total == null ? 0 : total;
    }

    /**
     * 真实耗时的采集通道：150ms 足够让槽位占满可观测，又不至于拖慢测试。
     *
     * <p>返回非零退出码而不是成功：本用例只验证"认领互斥/背压/慢车道"，
     * 不依赖采样落库；这也避免 H2 在并发 AUTO_INCREMENT 插入时出现重复主键
     * （测试环境限制，与调度逻辑无关）。失败路径同样会消耗真实耗时并写回退避时间。</p>
     */
    private static final class SlowRuntime implements OperationRuntime {
        private final Long userId;

        private SlowRuntime(Long userId) {
            this.userId = userId;
        }

        @Override public String id() { return "slow-runtime"; }
        @Override public Long userId() { return userId; }
        @Override public Long sessionId() { return 1L; }
        @Override public void write(String input) throws IOException { }
        @Override public void resize(int columns, int rows) throws IOException { }
        @Override public void onOutput(OutputListener listener) { }
        @Override public boolean isOpen() { return true; }
        @Override public void close() { }

        @Override
        public CommandResult execute(String command, long timeoutMillis) {
            try {
                Thread.sleep(150);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
            return new CommandResult(1, "", "simulated collection failure");
        }
    }
}
