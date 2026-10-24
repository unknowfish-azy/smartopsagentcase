package com.smartops.service;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

@Service
@RequiredArgsConstructor
public class ModelAnalyticsService {
    private final JdbcTemplate jdbc;
    private static final long MAX_TOKENS = 1_000_000_000_000L;

    public String start(Long userId, Long connectionId, String modelName) {
        String id = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO model_invocation_usage (id,user_id,connection_id,model_name,started_at,status) VALUES (?,?,?,?,?,?)",
                id, userId, connectionId, modelName, LocalDateTime.now(ZoneOffset.UTC), "PENDING");
        return id;
    }

    public void finish(String id, boolean success, long durationMs, Map<String, Object> usage) {
        Map<String, Object> values = usage == null ? Map.of() : usage;
        Long input = tokens(values.get("prompt_tokens"));
        Long output = tokens(values.get("completion_tokens"));
        Long total = tokens(values.get("total_tokens"));
        if (total == null && input != null && output != null) total = input + output;
        jdbc.update("UPDATE model_invocation_usage SET status=?,duration_ms=?,input_tokens=?,output_tokens=?,total_tokens=? WHERE id=? AND status='PENDING'",
                success ? "SUCCESS" : "FAILED", Math.max(0, durationMs), input, output, total, id);
    }

    private Long tokens(Object value) {
        if (!(value instanceof Number)) return null;
        try {
            long number = new BigDecimal(value.toString()).longValueExact();
            return number >= 0 && number <= MAX_TOKENS ? number : null;
        } catch (ArithmeticException | NumberFormatException ex) { return null; }
    }

    public Long budget(Long userId, YearMonth month) {
        List<Long> values = jdbc.query("SELECT token_limit FROM model_token_budget WHERE user_id=? AND budget_month=?",
                (rs, index) -> rs.getObject(1, Long.class), userId, month.toString());
        return values.isEmpty() ? null : values.get(0);
    }

    @Transactional
    public void saveBudget(Long userId, YearMonth month, Long limit) {
        if (limit != null && (limit < 0 || limit > MAX_TOKENS)) throw new IllegalArgumentException("额度需为 0–1000000000000 的整数");
        jdbc.update("INSERT INTO model_token_budget (user_id,budget_month,token_limit) VALUES (?,?,?) ON DUPLICATE KEY UPDATE token_limit=VALUES(token_limit)", userId, month.toString(), limit);
    }

    public Map<String, Object> report(Long userId, YearMonth month, Long connectionId) {
        String filter = connectionId == null ? "" : " AND connection_id=?";
        // DATETIME stores UTC wall-clock values; avoid Timestamp/JDBC session-zone conversion.
        List<Object> args = new ArrayList<>(List.of(userId, month.atDay(1).atStartOfDay(), month.plusMonths(1).atDay(1).atStartOfDay()));
        if (connectionId != null) args.add(connectionId);
        String metrics = "COUNT(*) AS calls, SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS successes, "
                + "SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failures, SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) AS pending, "
                + "SUM(CASE WHEN status<>'PENDING' AND total_tokens IS NULL THEN 1 ELSE 0 END) AS unknown_usage, "
                + "SUM(input_tokens) AS inputs, SUM(output_tokens) AS outputs, SUM(total_tokens) AS tokens, "
                + "AVG(CASE WHEN status='SUCCESS' THEN duration_ms ELSE NULL END) AS latency";
        String where = " FROM model_invocation_usage WHERE user_id=? AND started_at>=? AND started_at<?" + filter;
        Map<String, Object> summary = jdbc.queryForObject("SELECT " + metrics + where, (rs, row) -> metricRow(rs), args.toArray());
        List<Map<String, Object>> rawDays = jdbc.query("SELECT CAST(started_at AS DATE) AS usage_date," + metrics + where + " GROUP BY CAST(started_at AS DATE) ORDER BY usage_date", (rs, row) -> {
            Map<String,Object> value = metricRow(rs); value.put("date", rs.getObject("usage_date", LocalDate.class).toString()); return value;
        }, args.toArray());
        Map<String, Map<String,Object>> indexed = new HashMap<>();
        rawDays.forEach(day -> indexed.put((String) day.get("date"), day));
        List<Map<String,Object>> daily = new ArrayList<>();
        LocalDate today = LocalDate.now(ZoneOffset.UTC);
        for (int day = 1; day <= month.lengthOfMonth(); day++) {
            LocalDate date = month.atDay(day);
            Map<String,Object> item = indexed.get(date.toString());
            if (item == null) {
                item = new LinkedHashMap<>();
                item.put("date", date.toString()); item.put("calls", 0L); item.put("successes", 0L); item.put("failures", 0L);
                item.put("pendingCalls", 0L); item.put("unknownUsageCalls", 0L); item.put("knownTokens", date.isAfter(today) ? null : 0L);
                item.put("inputTokens", date.isAfter(today) ? null : 0L); item.put("outputTokens", date.isAfter(today) ? null : 0L);
                item.put("successRate", null); item.put("averageLatencyMs", null);
            }
            daily.add(item);
        }
        List<Map<String,Object>> models = jdbc.query("SELECT connection_id,model_name," + metrics + where + " GROUP BY connection_id,model_name ORDER BY calls DESC", (rs, row) -> {
            Map<String,Object> item = metricRow(rs); item.put("connectionId", rs.getLong("connection_id")); item.put("modelName", rs.getString("model_name")); return item;
        }, args.toArray());
        Map<String,Object> report = new LinkedHashMap<>();
        report.put("month", month.toString()); report.put("timezone", "UTC"); report.put("summary", summary);
        report.put("daily", daily); report.put("models", models); report.put("budget", budget(userId, month));
        Long allKnown = jdbc.queryForObject("SELECT COALESCE(SUM(total_tokens),0) FROM model_invocation_usage WHERE user_id=? AND started_at>=? AND started_at<?", Long.class, args.get(0),args.get(1),args.get(2));
        Long allUnknown = jdbc.queryForObject("SELECT COUNT(*) FROM model_invocation_usage WHERE user_id=? AND started_at>=? AND started_at<? AND (total_tokens IS NULL OR status='PENDING')", Long.class,args.get(0),args.get(1),args.get(2));
        report.put("budgetUsedTokens", allKnown); report.put("budgetUnknownCalls", allUnknown);
        return report;
    }

    private Map<String,Object> metricRow(java.sql.ResultSet rs) throws java.sql.SQLException {
        long calls = rs.getLong("calls"), successes = rs.getLong("successes"), failures = rs.getLong("failures");
        Map<String,Object> value = new LinkedHashMap<>();
        value.put("calls", calls); value.put("successes", successes); value.put("failures", failures);
        value.put("pendingCalls", rs.getLong("pending")); value.put("unknownUsageCalls", rs.getLong("unknown_usage"));
        value.put("knownTokens", tokenSum(rs, "tokens", calls));
        value.put("inputTokens", tokenSum(rs, "inputs", calls));
        value.put("outputTokens", tokenSum(rs, "outputs", calls));
        value.put("successRate", successes + failures == 0 ? null : successes * 100.0 / (successes + failures));
        value.put("averageLatencyMs", rs.getObject("latency") == null ? null : rs.getDouble("latency"));
        return value;
    }

    private Long tokenSum(java.sql.ResultSet rs, String column, long calls) throws java.sql.SQLException {
        Long total = rs.getObject(column, Long.class);
        if (total != null) return total;
        if (calls == 0) return 0L;
        return null;
    }
}
