package com.smartops.finops;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-14：成本按币种/标签归集、趋势、建议采样门槛、预算超支与环比异常。
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:finops_service;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class FinOpsServiceIntegrationTest {

    private static final long OWNER = 121L;
    private static final Instant WINDOW_START = Instant.parse("2026-11-01T00:00:00Z");
    private static final Instant WINDOW_END = Instant.parse("2026-11-08T00:00:00Z");

    @Autowired JdbcTemplate jdbc;
    @Autowired FinOpsService finops;

    @BeforeEach
    void clean() {
        jdbc.update("DELETE FROM finops_budget");
        jdbc.update("DELETE FROM finops_usage_sample");
        jdbc.update("DELETE FROM finops_cost_record");
    }

    @Test
    @DisplayName("成本按币种与标签分别汇总，未打标签归 UNALLOCATED，不做汇率换算")
    void costsAreAggregatedPerCurrencyAndAllocation() {
        finops.ingestCosts(OWNER, "bill-2026-10", "2026-10", List.of(
                new FinOpsService.CostInput("vm-1", "web-1", "aliyun", "cn-hangzhou", 120000L, "usd", "team-a", "{}"),
                new FinOpsService.CostInput("vm-2", "web-2", "aliyun", "cn-hangzhou", 80000L, "USD", "team-a", "{}"),
                new FinOpsService.CostInput("vm-3", "batch-3", "aws", "us-east-1", 50000L, "EUR", null, null)));

        FinOpsService.SummaryView summary = finops.summary(OWNER, "2026-10");
        assertThat(summary.totals()).containsExactly(
                new FinOpsService.CurrencyTotal("EUR", 50000L, 1),
                new FinOpsService.CurrencyTotal("USD", 200000L, 2));
        assertThat(summary.groups()).anySatisfy(group -> {
            assertThat(group.currency()).isEqualTo("USD");
            assertThat(group.allocationKey()).isEqualTo("team-a");
            assertThat(group.unallocated()).isFalse();
            assertThat(group.amountMinor()).isEqualTo(200000L);
            assertThat(group.resourceCount()).isEqualTo(2);
        });
        assertThat(summary.unallocatedTotals()).containsExactly(new FinOpsService.CurrencyTotal("EUR", 50000L, 1));
        assertThat(summary.sources()).containsExactly("bill-2026-10");
        assertThat(summary.resourceCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("同批次重放更新而非重复入账；非法账期/币种/金额被拒绝")
    void costIngestionIsIdempotentAndValidated() {
        FinOpsService.CostIngestView first = finops.ingestCosts(OWNER, "bill-1", "2026-10", List.of(
                new FinOpsService.CostInput("vm-1", "web", "aliyun", "cn", 100L, "USD", "team-a", null)));
        assertThat(first.accepted()).isEqualTo(1);
        assertThat(first.created()).isEqualTo(1);
        assertThat(first.updated()).isZero();

        FinOpsService.CostIngestView replay = finops.ingestCosts(OWNER, "bill-1", "2026-10", List.of(
                new FinOpsService.CostInput("vm-1", "web", "aliyun", "cn", 120L, "USD", "team-a", null)));
        assertThat(replay.created()).isZero();
        assertThat(replay.updated()).isEqualTo(1);
        assertThat(finops.summary(OWNER, "2026-10").totals()).singleElement()
                .satisfies(total -> assertThat(total.amountMinor()).isEqualTo(120L));

        assertThatThrownBy(() -> finops.ingestCosts(OWNER, "bill-2", "2026-13", List.of(
                new FinOpsService.CostInput("vm-1", null, null, null, 1L, "USD", null, null))))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_MONTH_INVALID");
        assertThatThrownBy(() -> finops.ingestCosts(OWNER, "bill-3", "2026-10", List.of(
                new FinOpsService.CostInput("vm-1", null, null, null, 1L, "US", null, null))))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_CURRENCY_INVALID");
        assertThatThrownBy(() -> finops.ingestCosts(OWNER, "bill-4", "2026-10", List.of(
                new FinOpsService.CostInput("vm-1", null, null, null, -1L, "USD", null, null))))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_AMOUNT_INVALID");
        assertThatThrownBy(() -> finops.ingestCosts(OWNER, "bill-5", "2026-10", List.of()))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_COST_EMPTY");
    }

    @Test
    @DisplayName("趋势只拼接真实存在的账期，不补零不预测")
    void trendOnlyUsesObservedMonths() {
        finops.ingestCosts(OWNER, "bill-09", "2026-09", List.of(
                new FinOpsService.CostInput("vm-1", null, null, null, 100L, "USD", "team-a", null)));
        finops.ingestCosts(OWNER, "bill-10", "2026-10", List.of(
                new FinOpsService.CostInput("vm-1", null, null, null, 150L, "USD", "team-a", null)));
        finops.ingestCosts(OWNER, "bill-11", "2026-11", List.of(
                new FinOpsService.CostInput("vm-1", null, null, null, 200L, "USD", "team-a", null)));

        List<FinOpsService.TrendPoint> trend = finops.trend(OWNER, 3);
        assertThat(trend).extracting(FinOpsService.TrendPoint::billingMonth)
                .containsExactly("2026-09", "2026-10", "2026-11");
        assertThat(trend).extracting(FinOpsService.TrendPoint::amountMinor)
                .containsExactly(100L, 150L, 200L);
        assertThatThrownBy(() -> finops.trend(OWNER, 0))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_TREND_MONTHS_INVALID");
    }

    @Test
    @DisplayName("利用率样本校验范围与来源")
    void usageSamplesAreValidated() {
        finops.recordUsage(OWNER, List.of(new FinOpsService.UsageInput(
                "vm-1", WINDOW_START, 10d, 20d, 50d, "collector-1")));
        assertThatThrownBy(() -> finops.recordUsage(OWNER, List.of(new FinOpsService.UsageInput(
                "vm-1", WINDOW_START, 120d, null, null, "collector-1"))))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_USAGE_RANGE_INVALID");
        assertThatThrownBy(() -> finops.recordUsage(OWNER, List.of(new FinOpsService.UsageInput(
                "vm-1", WINDOW_START, 10d, null, null, " "))))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_USAGE_SOURCE_REQUIRED");
        assertThatThrownBy(() -> finops.recordUsage(OWNER, List.of(new FinOpsService.UsageInput(
                "vm-1", WINDOW_START, null, null, null, "collector-1"))))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_USAGE_VALUE_REQUIRED");
        assertThatThrownBy(() -> finops.recordUsage(OWNER, List.of(new FinOpsService.UsageInput(
                "vm-1", null, 10d, null, null, "collector-1"))))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_USAGE_TIME_REQUIRED");
    }

    @Test
    @DisplayName("样本不足或覆盖不足只给采集建议；覆盖充分才给降配建议并附窗口与账单来源")
    void recommendationsRequireAdequateSampling() {
        finops.ingestCosts(OWNER, "bill-11", "2026-11", List.of(
                new FinOpsService.CostInput("vm-1", "web-1", "aliyun", "cn", 100000L, "USD", "team-a", null)));
        // 5 条样本：不足
        for (int index = 0; index < 5; index++) {
            insertUsage("vm-1", WINDOW_START.plus(Duration.ofHours(index * 30L)), 10d, 20d, 40d);
        }
        FinOpsService.RecommendationsView sparse = finops.recommendations(OWNER, "2026-11", WINDOW_START, WINDOW_END);
        assertThat(sparse.items()).singleElement().satisfies(item -> {
            assertThat(item.status()).isEqualTo("INSUFFICIENT_SAMPLES");
            assertThat(item.direction()).isEqualTo("COLLECT_MORE");
            assertThat(item.sampleCount()).isEqualTo(5);
            assertThat(item.costSources()).containsExactly("bill-11");
            assertThat(item.currency()).isEqualTo("USD");
            assertThat(item.monthlyAmountMinor()).isEqualTo(100000L);
            assertThat(item.estimatedSavingMinor()).isNull();
        });

        // 29 条但全挤在 1 小时内：覆盖不足
        jdbc.update("DELETE FROM finops_usage_sample");
        for (int index = 0; index < 29; index++) {
            insertUsage("vm-1", WINDOW_START.plus(Duration.ofMinutes(index * 2L)), 10d, 20d, 40d);
        }
        FinOpsService.RecommendationsView narrow = finops.recommendations(OWNER, "2026-11", WINDOW_START, WINDOW_END);
        assertThat(narrow.items()).singleElement().satisfies(item -> {
            assertThat(item.status()).isEqualTo("INSUFFICIENT_SAMPLES");
            assertThat(item.coverageRatio()).isLessThan(0.8);
        });

        // 29 条覆盖 7 天：可以给出降配建议
        jdbc.update("DELETE FROM finops_usage_sample");
        for (int index = 0; index < 29; index++) {
            insertUsage("vm-1", WINDOW_START.plus(Duration.ofHours(index * 6L)), 10d, 20d, 40d);
        }
        FinOpsService.RecommendationsView adequate = finops.recommendations(OWNER, "2026-11", WINDOW_START, WINDOW_END);
        assertThat(adequate.items()).singleElement().satisfies(item -> {
            assertThat(item.status()).isEqualTo("OVERPROVISIONED");
            assertThat(item.direction()).isEqualTo("RIGHTSIZE_DOWN");
            assertThat(item.sampleCount()).isEqualTo(29);
            assertThat(item.coverageRatio()).isEqualTo(1d);
            assertThat(item.windowStart()).isEqualTo(WINDOW_START);
            assertThat(item.windowEnd()).isEqualTo(WINDOW_END);
        });
    }

    @Test
    @DisplayName("空闲、磁盘压力与超载分别给出方向；无账单资源仍可评估但成本为空")
    void classificationsCoverIdleDiskAndUnderprovisioned() {
        insertSamples("idle-1", 3d, 5d, 30d);
        insertSamples("disk-1", 30d, 40d, 95d);
        insertSamples("hot-1", 90d, 70d, 60d);
        insertSamples("nocost-1", 10d, 20d, 40d);
        finops.ingestCosts(OWNER, "bill-11", "2026-11", List.of(
                new FinOpsService.CostInput("idle-1", "idle", null, null, 5000L, "USD", "team-a", null),
                new FinOpsService.CostInput("disk-1", "disk", null, null, 9000L, "EUR", "team-b", null),
                new FinOpsService.CostInput("hot-1", "hot", null, null, 15000L, "USD", null, null)));

        FinOpsService.RecommendationsView view = finops.recommendations(OWNER, "2026-11", WINDOW_START, WINDOW_END);
        assertThat(view.items()).hasSize(4);
        assertThat(view.items()).extracting(FinOpsService.Recommendation::resourceId)
                .containsExactly("disk-1", "hot-1", "idle-1", "nocost-1");
        assertThat(view.items()).anySatisfy(item -> {
            assertThat(item.resourceId()).isEqualTo("idle-1");
            assertThat(item.status()).isEqualTo("IDLE");
            assertThat(item.direction()).isEqualTo("STOP_OR_RIGHTSIZE");
        });
        assertThat(view.items()).anySatisfy(item -> {
            assertThat(item.resourceId()).isEqualTo("disk-1");
            assertThat(item.status()).isEqualTo("DISK_PRESSURE");
            assertThat(item.direction()).isEqualTo("EXPAND_DISK");
        });
        assertThat(view.items()).anySatisfy(item -> {
            assertThat(item.resourceId()).isEqualTo("hot-1");
            assertThat(item.status()).isEqualTo("UNDERPROVISIONED");
            assertThat(item.direction()).isEqualTo("RIGHTSIZE_UP");
            assertThat(item.unallocated()).isTrue();
        });
        assertThat(view.items()).anySatisfy(item -> {
            assertThat(item.resourceId()).isEqualTo("nocost-1");
            assertThat(item.currency()).isNull();
            assertThat(item.costSources()).isEmpty();
            assertThat(item.monthlyAmountMinor()).isZero();
        });

        assertThatThrownBy(() -> finops.recommendations(OWNER, "2026-11", WINDOW_END, WINDOW_START))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_WINDOW_INVALID");
        assertThatThrownBy(() -> finops.recommendations(OWNER, "2026-11",
                WINDOW_START, WINDOW_START.plus(Duration.ofDays(40))))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_WINDOW_INVALID");
    }

    @Test
    @DisplayName("预算超支与环比异常只基于真实历史，不跨币种、不对缺失上期做推断")
    void budgetsAndAnomaliesUseActualRecords() {
        finops.ingestCosts(OWNER, "bill-10", "2026-10", List.of(
                new FinOpsService.CostInput("vm-1", null, null, null, 90000L, "USD", "team-a", null),
                new FinOpsService.CostInput("vm-new", null, null, null, 10000L, "USD", "team-c", null)));
        finops.ingestCosts(OWNER, "bill-11", "2026-11", List.of(
                new FinOpsService.CostInput("vm-1", null, null, null, 120000L, "USD", "team-a", null),
                new FinOpsService.CostInput("vm-new", null, null, null, 10000L, "USD", "team-c", null),
                new FinOpsService.CostInput("vm-eur", null, null, null, 5000L, "EUR", "team-a", null)));

        finops.createBudget(OWNER, "team-a", "2026-11", "USD", 100000L, "team-a");
        FinOpsService.BudgetStatusView status = finops.budgetStatus(OWNER, "2026-11");
        assertThat(status.budgets()).singleElement().satisfies(budget -> {
            assertThat(budget.exceeded()).isTrue();
            assertThat(budget.actualMinor()).isEqualTo(120000L);
            assertThat(budget.budgetMinor()).isEqualTo(100000L);
            assertThat(budget.utilization()).isEqualTo(1.2d);
            assertThat(budget.costSources()).containsExactly("bill-11");
        });
        assertThat(status.anomalies()).anySatisfy(anomaly -> {
            assertThat(anomaly.kind()).isEqualTo("ALLOCATION_INCREASE");
            assertThat(anomaly.currency()).isEqualTo("USD");
            assertThat(anomaly.allocationKey()).isEqualTo("team-a");
            assertThat(anomaly.previousMinor()).isEqualTo(90000L);
            assertThat(anomaly.changeRatio()).isEqualTo(0.3333d);
        });
        assertThat(status.anomalies()).noneSatisfy(anomaly ->
                assertThat(anomaly.allocationKey()).isEqualTo("team-c"));

        assertThatThrownBy(() -> finops.createBudget(OWNER, "team-a", "2026-11", "USD", 100000L, "team-a"))
                .isInstanceOf(BusinessException.class).hasMessageContaining("FINOPS_BUDGET_EXISTS");
    }

    private void insertSamples(String resourceId, double cpu, double memory, double disk) {
        for (int index = 0; index < 29; index++) {
            insertUsage(resourceId, WINDOW_START.plus(Duration.ofHours(index * 6L)), cpu, memory, disk);
        }
    }

    private void insertUsage(String resourceId, Instant sampledAt, Double cpu, Double memory, Double disk) {
        jdbc.update("""
                INSERT INTO finops_usage_sample (user_id,resource_id,sampled_at,cpu_percent,memory_percent,disk_percent,source)
                VALUES (?,?,?,?,?,?,?)
                """, OWNER, resourceId, java.sql.Timestamp.from(sampledAt), cpu, memory, disk, "collector-1");
    }
}
