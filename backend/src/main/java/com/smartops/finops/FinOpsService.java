package com.smartops.finops;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.YearMonth;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * OPS-14：容量趋势、闲置/超配分析、标签成本归集、预算与成本异常。
 *
 * <p>只按真实账单与真实利用率样本给结论：
 * 金额按币种独立汇总（绝不跨币种相加），没有标签的记录归 UNALLOCATED；
 * 样本不足或覆盖不足时只给"继续采集"，不输出规格建议；缺少目标规格单价时不推算节省金额。</p>
 */
@Service
public class FinOpsService {

    /** 规格建议至少需要的样本数与窗口覆盖比例。 */
    public static final int MIN_SAMPLES = 24;
    public static final double COVERAGE_THRESHOLD = 0.8;
    private static final Pattern CURRENCY = Pattern.compile("[A-Z]{3}");
    private static final long MAX_WINDOW_SECONDS = 31L * 24 * 3600;

    private final JdbcTemplate jdbc;

    public FinOpsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /* ── 成本归集 ─────────────────────────────────────────────────────── */

    @Transactional
    public CostIngestView ingestCosts(long userId, String batchId, String billingMonth, List<CostInput> inputs) {
        if (!hasText(batchId)) throw new BusinessException(400, "FINOPS_BATCH_REQUIRED: 缺少账单批次 ID");
        String month = requireMonth(billingMonth);
        if (inputs == null || inputs.isEmpty()) {
            throw new BusinessException(400, "FINOPS_COST_EMPTY: 至少需要一条成本记录");
        }
        int created = 0, updated = 0, unallocated = 0;
        for (CostInput input : inputs) {
            if (input == null || !hasText(input.resourceId())) {
                throw new BusinessException(400, "FINOPS_RESOURCE_REQUIRED: 缺少资源 ID");
            }
            if (input.amountMinor() < 0) {
                throw new BusinessException(400, "FINOPS_AMOUNT_INVALID: 金额不能为负");
            }
            String currency = normalizeCurrency(input.currency());
            String allocation = trimToNull(input.allocationKey());
            if (allocation == null) unallocated++;
            Long existing = jdbc.query("""
                    SELECT id FROM finops_cost_record
                     WHERE user_id=? AND source_id=? AND resource_id=? AND billing_month=? AND currency=?
                    """, rs -> rs.next() ? rs.getLong(1) : null,
                    userId, batchId.trim(), input.resourceId().trim(), month, currency);
            if (existing == null) {
                jdbc.update("""
                        INSERT INTO finops_cost_record
                            (user_id,source_id,resource_id,resource_name,provider,region,billing_month,
                             amount_minor,currency,allocation_key,tags_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, userId, batchId.trim(), input.resourceId().trim(),
                        trimToNull(input.resourceName()), trimToNull(input.provider()), trimToNull(input.region()),
                        month, input.amountMinor(), currency, allocation, trimToNull(input.tagsJson()));
                created++;
            } else {
                jdbc.update("""
                        UPDATE finops_cost_record
                           SET amount_minor=?,resource_name=?,provider=?,region=?,allocation_key=?,tags_json=?,ingested_at=?
                         WHERE id=?
                        """, input.amountMinor(), trimToNull(input.resourceName()), trimToNull(input.provider()),
                        trimToNull(input.region()), allocation, trimToNull(input.tagsJson()),
                        Timestamp.from(Instant.now()), existing);
                updated++;
            }
        }
        return new CostIngestView(batchId.trim(), month, created + updated, created, updated, unallocated);
    }

    public SummaryView summary(long userId, String billingMonth) {
        String month = requireMonth(billingMonth);
        List<CostRow> rows = jdbc.query(
                "SELECT * FROM finops_cost_record WHERE user_id=? AND billing_month=?", COST_MAPPER, userId, month);
        Map<String, long[]> totals = new LinkedHashMap<>();
        Map<String, CostGroupAccumulator> groups = new LinkedHashMap<>();
        Map<String, long[]> unallocatedTotals = new LinkedHashMap<>();
        Set<String> sources = new LinkedHashSet<>();
        Set<String> resources = new LinkedHashSet<>();
        for (CostRow row : rows) {
            sources.add(row.sourceId());
            resources.add(row.resourceId());
            totals.computeIfAbsent(row.currency(), key -> new long[2]);
            totals.get(row.currency())[0] += row.amountMinor();
            totals.get(row.currency())[1]++;
            String key = row.currency() + "|" + (row.allocationKey() == null ? "" : row.allocationKey());
            CostGroupAccumulator group = groups.computeIfAbsent(key,
                    ignored -> new CostGroupAccumulator(row.currency(), row.allocationKey()));
            group.amountMinor += row.amountMinor();
            group.resources.add(row.resourceId());
            if (row.allocationKey() == null) {
                unallocatedTotals.computeIfAbsent(row.currency(), key2 -> new long[2]);
                unallocatedTotals.get(row.currency())[0] += row.amountMinor();
                unallocatedTotals.get(row.currency())[1]++;
            }
        }
        List<CurrencyTotal> totalViews = totals.entrySet().stream()
                .map(entry -> new CurrencyTotal(entry.getKey(), entry.getValue()[0], (int) entry.getValue()[1]))
                .sorted(Comparator.comparing(CurrencyTotal::currency)).toList();
        List<CostGroup> groupViews = groups.values().stream()
                .map(group -> new CostGroup(group.currency, group.allocationKey, group.allocationKey == null,
                        group.amountMinor, group.resources.size()))
                .sorted(Comparator.comparing(CostGroup::currency).thenComparing(
                        group -> group.allocationKey() == null ? "" : group.allocationKey())).toList();
        List<CurrencyTotal> unallocatedViews = unallocatedTotals.entrySet().stream()
                .map(entry -> new CurrencyTotal(entry.getKey(), entry.getValue()[0], (int) entry.getValue()[1]))
                .sorted(Comparator.comparing(CurrencyTotal::currency)).toList();
        return new SummaryView(month, totalViews, groupViews, unallocatedViews,
                List.copyOf(sources), resources.size());
    }

    public List<TrendPoint> trend(long userId, int months) {
        if (months < 1 || months > 12) {
            throw new BusinessException(400, "FINOPS_TREND_MONTHS_INVALID: 月份数需在 1..12");
        }
        String latest = jdbc.query("""
                SELECT MAX(billing_month) FROM finops_cost_record WHERE user_id=?
                """, rs -> rs.next() ? rs.getString(1) : null, userId);
        if (latest == null) return List.of();
        String cutoff = YearMonth.parse(latest).minusMonths(months - 1).toString();
        List<CostRow> rows = jdbc.query("""
                SELECT * FROM finops_cost_record WHERE user_id=? AND billing_month>=? ORDER BY billing_month,currency
                """, COST_MAPPER, userId, cutoff);
        Map<String, long[]> grouped = new LinkedHashMap<>();
        for (CostRow row : rows) {
            String key = row.billingMonth() + "|" + row.currency();
            grouped.computeIfAbsent(key, ignored -> new long[2]);
            grouped.get(key)[0] += row.amountMinor();
            grouped.get(key)[1]++;
        }
        List<TrendPoint> points = new ArrayList<>();
        grouped.forEach((key, value) -> {
            String[] parts = key.split("\\|", 2);
            points.add(new TrendPoint(parts[0], parts[1], value[0], (int) value[1]));
        });
        points.sort(Comparator.comparing(TrendPoint::billingMonth).thenComparing(TrendPoint::currency));
        return points;
    }

    /* ── 利用率样本 ───────────────────────────────────────────────────── */

    @Transactional
    public int recordUsage(long userId, List<UsageInput> inputs) {
        if (inputs == null || inputs.isEmpty()) {
            throw new BusinessException(400, "FINOPS_USAGE_EMPTY: 至少需要一条利用率样本");
        }
        for (UsageInput input : inputs) {
            if (input == null || !hasText(input.resourceId()) || !hasText(input.source())) {
                throw new BusinessException(400, "FINOPS_USAGE_SOURCE_REQUIRED: 缺少资源 ID 或采集来源");
            }
            if (input.sampledAt() == null) {
                throw new BusinessException(400, "FINOPS_USAGE_TIME_REQUIRED: 缺少采样时间");
            }
            validatePercent(input.cpuPercent(), "cpu");
            validatePercent(input.memoryPercent(), "memory");
            validatePercent(input.diskPercent(), "disk");
            if (input.cpuPercent() == null && input.memoryPercent() == null && input.diskPercent() == null) {
                throw new BusinessException(400, "FINOPS_USAGE_VALUE_REQUIRED: 至少需要一个利用率指标");
            }
            jdbc.update("""
                    DELETE FROM finops_usage_sample WHERE user_id=? AND resource_id=? AND sampled_at=?
                    """, userId, input.resourceId().trim(), Timestamp.from(input.sampledAt()));
            jdbc.update("""
                    INSERT INTO finops_usage_sample
                        (user_id,resource_id,sampled_at,cpu_percent,memory_percent,disk_percent,source)
                    VALUES (?,?,?,?,?,?,?)
                    """, userId, input.resourceId().trim(), Timestamp.from(input.sampledAt()),
                    input.cpuPercent(), input.memoryPercent(), input.diskPercent(), input.source().trim());
        }
        return inputs.size();
    }

    /* ── 规格建议 ─────────────────────────────────────────────────────── */

    public RecommendationsView recommendations(long userId, String billingMonth, Instant windowStart,
                                               Instant windowEnd) {
        String month = requireMonth(billingMonth);
        if (windowStart == null || windowEnd == null) {
            throw new BusinessException(400, "FINOPS_WINDOW_REQUIRED: 需要采样窗口开始与结束时间");
        }
        long windowSeconds = windowEnd.getEpochSecond() - windowStart.getEpochSecond();
        if (windowSeconds <= 0 || windowSeconds > MAX_WINDOW_SECONDS) {
            throw new BusinessException(400, "FINOPS_WINDOW_INVALID: 窗口需大于 0 且不超过 31 天");
        }
        List<CostRow> costs = jdbc.query("""
                SELECT * FROM finops_cost_record WHERE user_id=? AND billing_month=?
                """, COST_MAPPER, userId, month);

        Map<String, List<CostRow>> costGroups = new LinkedHashMap<>();
        for (CostRow row : costs) {
            String key = row.resourceId() + "|" + row.currency() + "|"
                    + (row.allocationKey() == null ? "" : row.allocationKey());
            costGroups.computeIfAbsent(key, ignored -> new ArrayList<>()).add(row);
        }
        Map<String, List<UsageRow>> usage = new LinkedHashMap<>();
        jdbc.query("""
                SELECT * FROM finops_usage_sample
                 WHERE user_id=? AND sampled_at>=? AND sampled_at<=?
                 ORDER BY resource_id,sampled_at
                """, USAGE_MAPPER, userId, Timestamp.from(windowStart), Timestamp.from(windowEnd))
                .forEach(row -> usage.computeIfAbsent(row.resourceId(), ignored -> new ArrayList<>()).add(row));

        Set<String> resourceIds = new LinkedHashSet<>();
        costGroups.keySet().forEach(key -> resourceIds.add(key.split("\\|", 2)[0]));
        resourceIds.addAll(usage.keySet());

        List<Recommendation> items = new ArrayList<>();
        for (String resourceId : resourceIds) {
            List<CostRow> resourceCosts = costGroups.entrySet().stream()
                    .filter(entry -> entry.getKey().startsWith(resourceId + "|"))
                    .flatMap(entry -> entry.getValue().stream()).toList();
            List<UsageRow> samples = usage.getOrDefault(resourceId, List.of());
            Stats stats = Stats.of(samples, windowStart, windowEnd);
            if (resourceCosts.isEmpty()) {
                items.add(describe(resourceId, null, null, null, 0L, List.of(), stats, windowStart, windowEnd));
                continue;
            }
            Map<String, List<CostRow>> byCurrencyAndAllocation = new LinkedHashMap<>();
            for (CostRow row : resourceCosts) {
                byCurrencyAndAllocation.computeIfAbsent(row.currency() + "|"
                        + (row.allocationKey() == null ? "" : row.allocationKey()), ignored -> new ArrayList<>())
                        .add(row);
            }
            byCurrencyAndAllocation.values().forEach(group -> {
                CostRow first = group.get(0);
                long amount = group.stream().mapToLong(CostRow::amountMinor).sum();
                List<String> sources = group.stream().map(CostRow::sourceId).distinct().toList();
                items.add(describe(resourceId, first.resourceName(), first.currency(), first.allocationKey(),
                        amount, sources, stats, windowStart, windowEnd));
            });
        }
        items.sort(Comparator.comparing(Recommendation::resourceId).thenComparing(
                item -> item.currency() == null ? "" : item.currency()));
        return new RecommendationsView(month, windowStart, windowEnd, MIN_SAMPLES, COVERAGE_THRESHOLD, items);
    }

    private Recommendation describe(String resourceId, String resourceName, String currency, String allocationKey,
                                    long amountMinor, List<String> sources, Stats stats,
                                    Instant windowStart, Instant windowEnd) {
        String status;
        String direction;
        String reason;
        if (stats.sampleCount < MIN_SAMPLES) {
            status = "INSUFFICIENT_SAMPLES";
            direction = "COLLECT_MORE";
            reason = "样本 " + stats.sampleCount + " 条，少于 " + MIN_SAMPLES + " 条，不产出规格建议";
        } else if (stats.coverage < COVERAGE_THRESHOLD) {
            status = "INSUFFICIENT_SAMPLES";
            direction = "COLLECT_MORE";
            reason = "样本仅覆盖窗口 " + Math.round(stats.coverage * 100) + "%，低于 "
                    + Math.round(COVERAGE_THRESHOLD * 100) + "%";
        } else if (stats.diskP95 != null && stats.diskP95 >= 90) {
            status = "DISK_PRESSURE";
            direction = "EXPAND_DISK";
            reason = "磁盘 P95 " + stats.diskP95 + "%，接近容量上限";
        } else if (stats.cpuP95 != null && stats.memoryP95 != null
                && stats.cpuP95 <= 5 && stats.memoryP95 <= 10) {
            status = "IDLE";
            direction = "STOP_OR_RIGHTSIZE";
            reason = "CPU P95 " + stats.cpuP95 + "%、内存 P95 " + stats.memoryP95 + "%，长期低负载";
        } else if (stats.cpuP95 != null && stats.memoryP95 != null
                && stats.cpuP95 <= 20 && stats.memoryP95 <= 30) {
            status = "OVERPROVISIONED";
            direction = "RIGHTSIZE_DOWN";
            reason = "CPU P95 " + stats.cpuP95 + "%、内存 P95 " + stats.memoryP95 + "%，存在降配空间";
        } else if ((stats.cpuP95 != null && stats.cpuP95 >= 85)
                || (stats.memoryP95 != null && stats.memoryP95 >= 90)) {
            status = "UNDERPROVISIONED";
            direction = "RIGHTSIZE_UP";
            reason = "CPU P95 " + stats.cpuP95 + "%、内存 P95 " + stats.memoryP95 + "%，接近饱和";
        } else {
            status = "NORMAL";
            direction = "KEEP";
            reason = "P95 处于合理区间";
        }
        return new Recommendation(resourceId, resourceName, currency, allocationKey,
                allocationKey == null && currency != null,
                amountMinor, sources, status, direction,
                reason + "；缺少目标规格单价，不推算节省金额",
                stats.windowStart, stats.windowEnd, stats.windowSeconds, stats.sampleCount,
                round(stats.coverage), stats.cpuP95, stats.memoryP95, stats.diskP95, null);
    }

    /* ── 预算与异常 ───────────────────────────────────────────────────── */

    public BudgetView createBudget(long userId, String name, String billingMonth, String currency,
                                   long amountMinor, String allocationKey) {
        if (!hasText(name)) throw new BusinessException(400, "FINOPS_BUDGET_NAME_REQUIRED: 缺少预算名称");
        String month = requireMonth(billingMonth);
        String normalized = normalizeCurrency(currency);
        if (amountMinor <= 0) throw new BusinessException(400, "FINOPS_BUDGET_AMOUNT_INVALID: 预算金额需大于 0");
        String allocation = trimToNull(allocationKey);
        Integer existing = jdbc.query("""
                SELECT id FROM finops_budget WHERE user_id=? AND name=? AND billing_month=?
                """, rs -> rs.next() ? rs.getInt(1) : null, userId, name.trim(), month);
        if (existing != null) throw new BusinessException(409, "FINOPS_BUDGET_EXISTS: 同名预算已存在");
        jdbc.update("""
                INSERT INTO finops_budget (user_id,name,billing_month,currency,amount_minor,allocation_key)
                VALUES (?,?,?,?,?,?)
                """, userId, name.trim(), month, normalized, amountMinor, allocation);
        return budgetView(requireBudget(userId, name.trim(), month));
    }

    public BudgetStatusView budgetStatus(long userId, String billingMonth) {
        String month = requireMonth(billingMonth);
        List<BudgetRow> budgets = jdbc.query(
                "SELECT * FROM finops_budget WHERE user_id=? AND billing_month=?", BUDGET_MAPPER, userId, month);
        List<BudgetStatus> statuses = new ArrayList<>();
        for (BudgetRow budget : budgets) {
            List<CostRow> costs = jdbc.query("""
                    SELECT * FROM finops_cost_record
                     WHERE user_id=? AND billing_month=? AND currency=?
                    """, COST_MAPPER, userId, month, budget.currency()).stream()
                    .filter(row -> budget.allocationKey() == null
                            || Objects.equals(budget.allocationKey(), row.allocationKey()))
                    .toList();
            long actual = costs.stream().mapToLong(CostRow::amountMinor).sum();
            List<String> sources = costs.stream().map(CostRow::sourceId).distinct().toList();
            statuses.add(new BudgetStatus(budget.id(), budget.name(), month, budget.currency(),
                    budget.allocationKey(), budget.amountMinor(), actual, actual > budget.amountMinor(),
                    budget.amountMinor() == 0 ? 0 : round((double) actual / budget.amountMinor()), sources));
        }
        return new BudgetStatusView(month, statuses, anomalies(userId, month));
    }

    private List<Anomaly> anomalies(long userId, String month) {
        String previous = YearMonth.parse(month).minusMonths(1).toString();
        List<CostRow> current = jdbc.query(
                "SELECT * FROM finops_cost_record WHERE user_id=? AND billing_month=?", COST_MAPPER, userId, month);
        List<CostRow> prior = jdbc.query(
                "SELECT * FROM finops_cost_record WHERE user_id=? AND billing_month=?", COST_MAPPER, userId, previous);
        Map<String, Long> currentByAllocation = aggregateByAllocation(current);
        Map<String, Long> priorByAllocation = aggregateByAllocation(prior);
        List<Anomaly> anomalies = new ArrayList<>();
        currentByAllocation.forEach((key, amount) -> {
            Long previousAmount = priorByAllocation.get(key);
            if (previousAmount == null || previousAmount == 0) return; // 缺上期数据不推断增长率
            double ratio = (double) (amount - previousAmount) / previousAmount;
            if (ratio >= 0.30) {
                String[] parts = key.split("\\|", 2);
                anomalies.add(new Anomaly("ALLOCATION_INCREASE", parts[0],
                        parts.length > 1 && !parts[1].isEmpty() ? parts[1] : null, null,
                        amount, previousAmount, round(ratio), "环比增长超过 30%"));
            }
        });
        Map<String, Long> currentByResource = aggregateByResource(current);
        Map<String, Long> priorByResource = aggregateByResource(prior);
        currentByResource.forEach((key, amount) -> {
            Long previousAmount = priorByResource.get(key);
            if (previousAmount == null || previousAmount == 0) return;
            double ratio = (double) (amount - previousAmount) / previousAmount;
            if (ratio >= 0.50) {
                String[] parts = key.split("\\|", 2);
                anomalies.add(new Anomaly("RESOURCE_INCREASE", parts[0], null, parts[1],
                        amount, previousAmount, round(ratio), "单资源环比增长超过 50%"));
            }
        });
        anomalies.sort(Comparator.comparing(Anomaly::currency).thenComparing(Anomaly::kind)
                .thenComparing(anomaly -> anomaly.allocationKey() == null ? "" : anomaly.allocationKey())
                .thenComparing(anomaly -> anomaly.resourceId() == null ? "" : anomaly.resourceId()));
        return anomalies;
    }

    private static Map<String, Long> aggregateByAllocation(List<CostRow> rows) {
        Map<String, Long> totals = new LinkedHashMap<>();
        rows.forEach(row -> totals.merge(
                row.currency() + "|" + (row.allocationKey() == null ? "" : row.allocationKey()),
                row.amountMinor(), Long::sum));
        return totals;
    }

    private static Map<String, Long> aggregateByResource(List<CostRow> rows) {
        Map<String, Long> totals = new LinkedHashMap<>();
        rows.forEach(row -> totals.merge(row.currency() + "|" + row.resourceId(), row.amountMinor(), Long::sum));
        return totals;
    }

    private BudgetRow requireBudget(long userId, String name, String month) {
        BudgetRow budget = jdbc.query("""
                SELECT * FROM finops_budget WHERE user_id=? AND name=? AND billing_month=?
                """, rs -> rs.next() ? BUDGET_MAPPER.mapRow(rs, 0) : null, userId, name, month);
        if (budget == null) throw new BusinessException(404, "FINOPS_BUDGET_NOT_FOUND: 预算不存在");
        return budget;
    }

    private BudgetView budgetView(BudgetRow row) {
        return new BudgetView(row.id(), row.name(), row.billingMonth(), row.currency(),
                row.allocationKey(), row.amountMinor());
    }

    /* ── 校验与工具 ───────────────────────────────────────────────────── */

    private static String requireMonth(String value) {
        if (!hasText(value)) throw new BusinessException(400, "FINOPS_MONTH_REQUIRED: 缺少账期 YYYY-MM");
        try {
            return YearMonth.parse(value.trim()).toString();
        } catch (DateTimeParseException invalid) {
            throw new BusinessException(400, "FINOPS_MONTH_INVALID: 账期需为 YYYY-MM");
        }
    }

    private static String normalizeCurrency(String value) {
        String normalized = value == null ? null : value.trim().toUpperCase(Locale.ROOT);
        if (normalized == null || !CURRENCY.matcher(normalized).matches()) {
            throw new BusinessException(400, "FINOPS_CURRENCY_INVALID: 币种需为 ISO 4217 三字母代码");
        }
        return normalized;
    }

    private static void validatePercent(Double value, String name) {
        if (value != null && (value < 0 || value > 100)) {
            throw new BusinessException(400, "FINOPS_USAGE_RANGE_INVALID: " + name + " 需在 0..100");
        }
    }

    private static boolean hasText(String value) { return value != null && !value.isBlank(); }

    private static String trimToNull(String value) { return hasText(value) ? value.trim() : null; }

    private static double round(double value) { return Math.round(value * 10000d) / 10000d; }

    private static Double percentile(List<Double> values) {
        if (values.isEmpty()) return null;
        List<Double> sorted = values.stream().filter(Objects::nonNull).sorted().toList();
        if (sorted.isEmpty()) return null;
        int index = (int) Math.ceil(0.95 * sorted.size()) - 1;
        return sorted.get(Math.max(0, Math.min(index, sorted.size() - 1)));
    }

    private static Instant instant(ResultSet rs, String column) throws java.sql.SQLException {
        Timestamp value = rs.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }

    private static Long nullableLong(ResultSet rs, String column) throws java.sql.SQLException {
        long value = rs.getLong(column);
        return rs.wasNull() ? null : value;
    }

    private record CostRow(long id, String sourceId, String resourceId, String resourceName, String provider,
                           String region, String billingMonth, long amountMinor, String currency,
                           String allocationKey) {}

    private record UsageRow(long id, String resourceId, Instant sampledAt, Double cpuPercent,
                            Double memoryPercent, Double diskPercent, String source) {}

    private record BudgetRow(long id, String name, String billingMonth, String currency, long amountMinor,
                             String allocationKey) {}

    private static final class CostGroupAccumulator {
        private final String currency;
        private final String allocationKey;
        private long amountMinor;
        private final Set<String> resources = new LinkedHashSet<>();

        private CostGroupAccumulator(String currency, String allocationKey) {
            this.currency = currency;
            this.allocationKey = allocationKey;
        }
    }

    private record Stats(Instant windowStart, Instant windowEnd, long windowSeconds, int sampleCount,
                         double coverage, Double cpuP95, Double memoryP95, Double diskP95) {
        static Stats of(List<UsageRow> samples, Instant windowStart, Instant windowEnd) {
            long seconds = windowEnd.getEpochSecond() - windowStart.getEpochSecond();
            if (samples.isEmpty()) {
                return new Stats(windowStart, windowEnd, seconds, 0, 0d, null, null, null);
            }
            Instant first = samples.get(0).sampledAt();
            Instant last = samples.get(samples.size() - 1).sampledAt();
            long covered = last.getEpochSecond() - first.getEpochSecond();
            double coverage = seconds == 0 ? 0d : Math.min(1d, (double) covered / seconds);
            return new Stats(windowStart, windowEnd, seconds, samples.size(), coverage,
                    percentile(samples.stream().map(UsageRow::cpuPercent).toList()),
                    percentile(samples.stream().map(UsageRow::memoryPercent).toList()),
                    percentile(samples.stream().map(UsageRow::diskPercent).toList()));
        }
    }

    private static final org.springframework.jdbc.core.RowMapper<CostRow> COST_MAPPER = (rs, rowNum) -> new CostRow(
            rs.getLong("id"), rs.getString("source_id"), rs.getString("resource_id"),
            rs.getString("resource_name"), rs.getString("provider"), rs.getString("region"),
            rs.getString("billing_month"), rs.getLong("amount_minor"), rs.getString("currency"),
            rs.getString("allocation_key"));

    private static final org.springframework.jdbc.core.RowMapper<UsageRow> USAGE_MAPPER = (rs, rowNum) -> new UsageRow(
            rs.getLong("id"), rs.getString("resource_id"), instant(rs, "sampled_at"),
            nullableDouble(rs, "cpu_percent"), nullableDouble(rs, "memory_percent"),
            nullableDouble(rs, "disk_percent"), rs.getString("source"));

    private static final org.springframework.jdbc.core.RowMapper<BudgetRow> BUDGET_MAPPER = (rs, rowNum) -> new BudgetRow(
            rs.getLong("id"), rs.getString("name"), rs.getString("billing_month"), rs.getString("currency"),
            rs.getLong("amount_minor"), rs.getString("allocation_key"));

    private static Double nullableDouble(ResultSet rs, String column) throws java.sql.SQLException {
        double value = rs.getDouble(column);
        return rs.wasNull() ? null : value;
    }

    /* ── 公开视图 ─────────────────────────────────────────────────────── */

    public record CostInput(String resourceId, String resourceName, String provider, String region,
                            long amountMinor, String currency, String allocationKey, String tagsJson) {}

    public record UsageInput(String resourceId, Instant sampledAt, Double cpuPercent, Double memoryPercent,
                             Double diskPercent, String source) {}

    public record CostIngestView(String batchId, String billingMonth, int accepted, int created, int updated,
                                 long unallocatedCount) {}

    public record CurrencyTotal(String currency, long amountMinor, int recordCount) {}

    public record CostGroup(String currency, String allocationKey, boolean unallocated, long amountMinor,
                            int resourceCount) {}

    public record SummaryView(String billingMonth, List<CurrencyTotal> totals, List<CostGroup> groups,
                              List<CurrencyTotal> unallocatedTotals, List<String> sources, int resourceCount) {}

    public record TrendPoint(String billingMonth, String currency, long amountMinor, int recordCount) {}

    public record Recommendation(String resourceId, String resourceName, String currency, String allocationKey,
                                 boolean unallocated, long monthlyAmountMinor, List<String> costSources,
                                 String status, String direction, String reason, Instant windowStart,
                                 Instant windowEnd, long windowSeconds, int sampleCount, double coverageRatio,
                                 Double cpuP95, Double memoryP95, Double diskP95, Long estimatedSavingMinor) {}

    public record RecommendationsView(String billingMonth, Instant windowStart, Instant windowEnd,
                                      int minSamples, double coverageThreshold, List<Recommendation> items) {}

    public record BudgetView(long id, String name, String billingMonth, String currency, String allocationKey,
                            long amountMinor) {}

    public record BudgetStatus(long budgetId, String name, String billingMonth, String currency,
                               String allocationKey, long budgetMinor, long actualMinor, boolean exceeded,
                               double utilization, List<String> costSources) {}

    public record Anomaly(String kind, String currency, String allocationKey, String resourceId,
                          long currentMinor, Long previousMinor, Double changeRatio, String reason) {}

    public record BudgetStatusView(String billingMonth, List<BudgetStatus> budgets, List<Anomaly> anomalies) {}
}
