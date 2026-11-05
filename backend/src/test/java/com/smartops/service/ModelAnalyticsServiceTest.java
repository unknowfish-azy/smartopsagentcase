package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import java.time.YearMonth;
import java.util.Map;
import java.util.UUID;
import static org.assertj.core.api.Assertions.*;

class ModelAnalyticsServiceTest {
    private JdbcTemplate jdbc;
    private ModelAnalyticsService service;
    @BeforeEach void setup() {
        var source = new DriverManagerDataSource("jdbc:h2:mem:analytics-" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        new ResourceDatabasePopulator(new ClassPathResource("db/migration/V20261001__model_analytics.sql")).execute(source);
        jdbc = new JdbcTemplate(source);
        service = new ModelAnalyticsService(jdbc);
    }
    @Test void recordsActualUsageAndSeparatesUsersMonthsAndUnknownUsage() {
        String a = service.start(7L, 1L, "model-a");
        service.finish(a, true, 120L, Map.of("prompt_tokens", 10, "completion_tokens", 4, "total_tokens", 14));
        String b = service.start(7L, 1L, "model-a");
        service.finish(b, false, 80L, Map.of());
        String c = service.start(7L, 2L, "model-b");
        service.finish(c, true, 200L, Map.of("total_tokens", 8));
        service.finish(service.start(8L, 1L, "other"), true, 10L, Map.of("total_tokens", 999));
        var report = service.report(7L, YearMonth.now(java.time.ZoneOffset.UTC), null);
        var summary = (Map<?, ?>) report.get("summary");
        assertThat(summary.get("calls")).isEqualTo(3L);
        assertThat(summary.get("knownTokens")).isEqualTo(22L);
        assertThat(summary.get("unknownUsageCalls")).isEqualTo(1L);
        assertThat(summary.get("successRate")).isEqualTo(200.0 / 3);
        assertThat(((Map<?, ?>) service.report(7L, YearMonth.now(java.time.ZoneOffset.UTC), 2L).get("summary")).get("calls")).isEqualTo(1L);
        assertThat(((Map<?, ?>) service.report(7L, YearMonth.now(java.time.ZoneOffset.UTC).minusMonths(1), null).get("summary")).get("calls")).isEqualTo(0L);
        assertThat(report.toString()).doesNotContain("prompt_tokens", "apiKey");
    }
    @Test void missingUsageIsNotAZeroAndBudgetIsUserOwned() {
        String id = service.start(1L, 2L, "model");
        service.finish(id, true, 50, Map.of("total_tokens", -1, "prompt_tokens", 1.5));
        var month = YearMonth.now(java.time.ZoneOffset.UTC);
        var summary = (Map<?, ?>) service.report(1L, month, null).get("summary");
        assertThat(summary.get("unknownUsageCalls")).isEqualTo(1L);
        service.saveBudget(1L, month, 1000L);
        assertThat(service.budget(1L, month)).isEqualTo(1000L);
        assertThat(service.budget(2L, month)).isNull();
        service.saveBudget(1L, month, 0L);
        assertThat(service.budget(1L, month)).isEqualTo(0L);
        service.saveBudget(1L, month, null);
        assertThat(service.budget(1L, month)).isNull();
        assertThatThrownBy(() -> service.saveBudget(1L, month, -1L)).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void pendingCallsAreNotCountedAsFailuresAndFinishIsIdempotent() {
        String id = service.start(1L, 1L, "model");
        var month = YearMonth.now(java.time.ZoneOffset.UTC);
        var pending = (Map<?, ?>) service.report(1L, month, null).get("summary");
        assertThat(pending.get("pendingCalls")).isEqualTo(1L);
        assertThat(pending.get("successRate")).isNull();
        service.finish(id, true, 20L, Map.of("prompt_tokens", 2, "completion_tokens", 3));
        service.finish(id, false, 99L, Map.of());
        var summary = (Map<?, ?>) service.report(1L, month, null).get("summary");
        assertThat(summary.get("knownTokens")).isEqualTo(5L);
        assertThat(summary.get("successRate")).isEqualTo(100.0);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM model_invocation_usage", Long.class)).isEqualTo(1L);
    }

    @Test void utcDayAndMonthBoundariesRemainStableAcrossJvmTimezones() {
        var original = java.util.TimeZone.getDefault();
        try {
            for (String zone : new String[]{"UTC", "Asia/Shanghai", "America/Los_Angeles"}) {
                java.util.TimeZone.setDefault(java.util.TimeZone.getTimeZone(zone));
                jdbc.update("DELETE FROM model_invocation_usage");
                String before = service.start(1L, 1L, "model");
                String last = service.start(1L, 1L, "model");
                String next = service.start(1L, 1L, "model");
                service.finish(before, true, 1, Map.of("total_tokens", 1));
                service.finish(last, true, 2, Map.of("total_tokens", 2));
                service.finish(next, true, 3, Map.of("total_tokens", 3));
                jdbc.update("UPDATE model_invocation_usage SET started_at=? WHERE id=?", java.time.LocalDateTime.parse("2026-08-31T23:59:59"), before);
                jdbc.update("UPDATE model_invocation_usage SET started_at=? WHERE id=?", java.time.LocalDateTime.parse("2026-09-30T23:59:59"), last);
                jdbc.update("UPDATE model_invocation_usage SET started_at=? WHERE id=?", java.time.LocalDateTime.parse("2026-10-01T00:00:00"), next);
                var report = service.report(1L, YearMonth.of(2026, 9), null);
                assertThat(((Map<?, ?>) report.get("summary")).get("knownTokens")).isEqualTo(2L);
                var daily = (java.util.List<Map<String, Object>>) report.get("daily");
                assertThat(daily.get(29).get("knownTokens")).isEqualTo(2L);
                long dailyTotal = daily.stream().map(day -> (Number) day.get("knownTokens")).filter(java.util.Objects::nonNull).mapToLong(Number::longValue).sum();
                assertThat(dailyTotal).isEqualTo(((Number) ((Map<?, ?>) report.get("summary")).get("knownTokens")).longValue());
                assertThat(report.get("budgetUsedTokens")).isEqualTo(2L);
            }
        } finally { java.util.TimeZone.setDefault(original); }
    }
}
