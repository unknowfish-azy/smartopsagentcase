package com.smartops.diagnostics;

import com.smartops.assistant.MiniAssistantEngine;
import com.smartops.config.BusinessSchemaHealthIndicator;
import com.smartops.security.SessionUser;
import com.smartops.service.HarborCatalogService;
import com.smartops.service.ObservabilityService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

class HealthDiagnosticServiceTest {
    private JdbcTemplate jdbc;
    private BusinessSchemaHealthIndicator schema;
    private DiagnosticTargetPolicy targets;
    private MiniAssistantEngine mini;
    private ObservabilityService observability;
    private HarborCatalogService harbor;
    private HealthDiagnosticService service;

    @BeforeEach
    void setUp() {
        jdbc = mock(JdbcTemplate.class);
        schema = mock(BusinessSchemaHealthIndicator.class);
        targets = new DiagnosticTargetPolicy(new DiagnosticTargetProperties());
        mini = mock(MiniAssistantEngine.class);
        observability = mock(ObservabilityService.class);
        harbor = mock(HarborCatalogService.class);
        when(mini.status()).thenReturn(new MiniAssistantEngine.RuntimeStatus(true, "ready", "本地运行时可用", "mini"));
        when(observability.sources()).thenReturn(List.of(new ObservabilityService.SourceStatus("prometheus", false, false)));
        when(harbor.status()).thenReturn(new HarborCatalogService.SourceStatus(false, false));
        service = new HealthDiagnosticService(jdbc, schema, targets, mini, observability, harbor);
    }

    @Test
    void userSummaryDoesNotExposeDatabaseOrGlobalDetails() {
        var result = service.summary(new SessionUser(11L, "operator", "operator", "user", false, 0));

        assertThat(result.scope()).isEqualTo("user");
        assertThat(result.policy()).isNull();
        assertThat(new com.fasterxml.jackson.databind.ObjectMapper().valueToTree(result).has("policy")).isFalse();
        assertThat(result.checks()).extracting(HealthDiagnosticService.Check::id)
                .containsExactly("session", "mini", "authorized-targets");
        assertThat(result.checks()).allMatch(check -> !check.summary().contains("app_user"));
        verifyNoInteractions(jdbc, schema, observability, harbor);
    }

    @Test
    void healthyDatabaseStillReportsMissingBusinessTablesAsUnhealthy() {
        when(jdbc.queryForObject("SELECT 1", Integer.class)).thenReturn(1);
        when(schema.missingTables()).thenReturn(List.of("knowledge_candidate"));

        var result = service.adminSummary(new SessionUser(1L, "admin", "admin", "admin", false, 0));

        assertThat(check(result, "database").status()).isEqualTo("HEALTHY");
        assertThat(check(result, "schema").status()).isEqualTo("UNHEALTHY");
        assertThat(check(result, "schema").summary()).contains("knowledge_candidate");
    }

    @Test
    void databaseFailureLeavesSchemaAsNotChecked() {
        when(jdbc.queryForObject("SELECT 1", Integer.class)).thenThrow(new IllegalStateException("database unavailable"));

        var result = service.adminSummary(new SessionUser(1L, "admin", "admin", "admin", false, 0));

        assertThat(check(result, "database").status()).isEqualTo("UNHEALTHY");
        assertThat(check(result, "schema").status()).isEqualTo("NOT_CHECKED");
        verifyNoInteractions(schema);
    }

    @Test
    void schemaMetadataFailureIsNotReportedAsHealthy() {
        when(jdbc.queryForObject("SELECT 1", Integer.class)).thenReturn(1);
        when(schema.missingTables()).thenThrow(new IllegalStateException("metadata unavailable"));

        var result = service.adminSummary(new SessionUser(1L, "admin", "admin", "admin", false, 0));

        assertThat(check(result, "schema").status()).isEqualTo("NOT_CHECKED");
    }

    @Test
    void administratorResultsRequireAdminPortalAndPermanentPassword() {
        assertThatThrownBy(() -> service.adminSummary(new SessionUser(1L, "admin", "admin", "user", false, 0)))
                .isInstanceOf(org.springframework.security.access.AccessDeniedException.class);
        assertThatThrownBy(() -> service.adminSummary(new SessionUser(1L, "admin", "admin", "admin", true, 0)))
                .isInstanceOf(org.springframework.security.access.AccessDeniedException.class);
    }

    private static HealthDiagnosticService.Check check(HealthDiagnosticService.Summary summary, String id) {
        return summary.checks().stream().filter(item -> item.id().equals(id)).findFirst().orElseThrow();
    }

    @Test
    void adminSummaryContainsOnlySafePolicyLimitsAndConfigurationFlags() throws Exception {
        when(jdbc.queryForObject("SELECT 1", Integer.class)).thenReturn(1);
        when(schema.missingTables()).thenReturn(List.of());
        var result = service.adminSummary(new SessionUser(1L, "admin", "admin", "admin", false, 0));
        assertThat(result.policy()).isNotNull();
        var json = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(result.policy());
        assertThat(json).contains("targetCount", "perUserConcurrency", "globalConcurrency", "connectTimeoutMs", "readTimeoutMs", "maxResponseBytes");
        assertThat(json).doesNotContainIgnoringCase("token", "password", "authorization", "cookie", "hostname", "pinned");
        var tree = new com.fasterxml.jackson.databind.ObjectMapper().readTree(json);
        var keys = new java.util.HashSet<String>();
        tree.fieldNames().forEachRemaining(keys::add);
        assertThat(keys).containsExactlyInAnyOrder("targetCount", "perUserConcurrency", "globalConcurrency", "connectTimeoutMs", "readTimeoutMs", "maxResponseBytes", "miniConfigured", "observabilityConfigured", "harborConfigured");
        tree.elements().forEachRemaining(value -> assertThat(value.isNumber() || value.isBoolean()).isTrue());
        assertThat(result.policy().perUserConcurrency()).isEqualTo(DiagnosticProbeLimiter.PER_USER_LIMIT);
        assertThat(result.policy().maxResponseBytes()).isEqualTo(DiagnosticTransport.MAX_BODY_BYTES);
    }

}
