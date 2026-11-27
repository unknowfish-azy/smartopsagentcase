package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.service.modelconfig.ModelConfigRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.startsWith;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import java.util.List;
import java.util.Map;

class ModelGatewayServiceTest {
    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final ModelConnectionService connections = mock(ModelConnectionService.class);
    private final ModelSemanticCacheService cache = mock(ModelSemanticCacheService.class);
    private final ModelRouterService router = mock(ModelRouterService.class);
    private final ModelConfigRegistry configRegistry = mock(ModelConfigRegistry.class);
    private final ModelGatewayService gateway = new ModelGatewayService(jdbc, connections, cache, router, configRegistry, 60L);

    private void stubKeyUnlimited() {
        when(jdbc.query(contains("model_gateway_key WHERE id=?"), any(RowMapper.class), eq(4L)))
                .thenReturn(List.of(Map.of("requests", -1L, "tokens", -1L)));
    }

    private void stubNoGroupLimits() {
        when(jdbc.query(contains("model_gateway_group WHERE slug=?"), any(RowMapper.class), eq("ops"), eq(9L)))
                .thenReturn(List.of());
    }

    /** 近 24h 消耗（calls/tokens）与近 60 秒请求数（recent）。 */
    private void stubUsage(long calls, long tokens, long recent) {
        when(jdbc.query(contains("COUNT(*) calls"), any(RowMapper.class), eq(4L)))
                .thenReturn(List.of(Map.of("calls", calls, "tokens", tokens, "recent", recent)));
    }

    @Test void unsupportedScopeCannotIssueKey() {
        assertEquals(400, assertThrows(BusinessException.class,
                () -> gateway.issueKey(1L, "team key", "TEAM", Instant.now().plusSeconds(3600))).getCode());
        verifyNoInteractions(jdbc);
    }

    @Test void expiredKeyCannotBeIssued() {
        assertEquals(400, assertThrows(BusinessException.class,
                () -> gateway.issueKey(1L, "expired", "PERSONAL", Instant.now().minusSeconds(1))).getCode());
        verifyNoInteractions(jdbc);
    }

    @Test void invalidGroupSlugCannotConfigureRoute() {
        assertEquals(400, assertThrows(BusinessException.class,
                () -> gateway.configureGroup(1L, "../other", "other", 1L)).getCode());
        verifyNoInteractions(jdbc, connections);
    }

    @Test void invocationFallsBackToNextEnabledRouteAfterProviderFailure() {
        var principal = new ModelGatewayService.GatewayPrincipal(4L, 9L, "PERSONAL");
        stubKeyUnlimited();
        stubNoGroupLimits();
        stubUsage(0, 0, 0);
        // 路由已委托 ModelRouterService：主路由失败后回退到下一个候选连接
        when(router.selectConnections(eq("ops"), eq(9L), any(ModelInvocationRequest.class)))
                .thenReturn(List.of(
                        new ModelRouterService.RoutedConnection(11L, 101L, "MANUAL route", 1.0),
                        new ModelRouterService.RoutedConnection(12L, 102L, "MANUAL route", 1.0)));
        when(connections.invoke(eq(9L), eq(11L), any(ModelInvocationRequest.class)))
                .thenThrow(new IllegalStateException("provider down"));
        when(connections.invoke(eq(9L), eq(12L), any(ModelInvocationRequest.class)))
                .thenReturn(ModelInvocationResponse.builder().model("backup").content("ok").usage(Map.of()).build());

        var result = gateway.invoke(principal, "ops", new ModelInvocationRequest());

        assertEquals("ok", result.getContent());
    }

    @Test void auditRecordsResolvedConfigVersionInsteadOfStable() {
        var principal = new ModelGatewayService.GatewayPrincipal(4L, 9L, "PERSONAL");
        stubKeyUnlimited();
        stubNoGroupLimits();
        stubUsage(0, 0, 0);
        when(router.selectConnections(eq("ops"), eq(9L), any(ModelInvocationRequest.class)))
                .thenReturn(List.of(new ModelRouterService.RoutedConnection(12L, null, "MANUAL route", 1.0)));
        when(connections.invoke(eq(9L), eq(12L), any(ModelInvocationRequest.class)))
                .thenReturn(ModelInvocationResponse.builder().model("backup").content("ok").usage(Map.of()).build());
        // 灰度分桶把该用户分到 v7：审计必须记录 7，而不是 stable 版本号
        when(configRegistry.resolveVersion(9L, "ops")).thenReturn(7);

        gateway.invoke(principal, "ops", new ModelInvocationRequest());

        org.mockito.ArgumentCaptor<Object[]> args = org.mockito.ArgumentCaptor.forClass(Object[].class);
        verify(jdbc).update(startsWith("INSERT INTO model_gateway_invocation"), args.capture());
        assertEquals(7, args.getValue()[4]);
    }

    @Test void groupQuotaStillAppliesWhenKeyHasNoLimit() {
        var principal = new ModelGatewayService.GatewayPrincipal(4L, 9L, "PERSONAL");
        stubKeyUnlimited();
        stubUsage(0, 0, 0);
        when(jdbc.query(contains("model_gateway_group WHERE slug=?"), any(RowMapper.class), eq("ops"), eq(9L)))
                .thenReturn(List.of(Map.of("requests", 5L, "tokens", -1L)));
        when(jdbc.query(contains("COUNT(*) calls"), any(RowMapper.class), eq(9L), eq("ops")))
                .thenReturn(List.of(Map.of("calls", 5L, "tokens", 0L)));

        assertEquals(429, assertThrows(BusinessException.class,
                () -> gateway.invoke(principal, "ops", new ModelInvocationRequest())).getCode());
    }

    @Test void perMinuteRateLimitRejectsBurstAndWritesAudit() {
        var principal = new ModelGatewayService.GatewayPrincipal(4L, 9L, "PERSONAL");
        stubKeyUnlimited();
        stubNoGroupLimits();
        stubUsage(0, 0, 60);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> gateway.invoke(principal, "ops", new ModelInvocationRequest()));
        assertEquals(429, failure.getCode());
        assertTrue(failure.getMessage().contains("rate limit"));

        // 拒绝也留痕：审计表写入 REJECTED_RATE_LIMITED，便于事后归因
        org.mockito.ArgumentCaptor<Object[]> args = org.mockito.ArgumentCaptor.forClass(Object[].class);
        verify(jdbc).update(startsWith("INSERT INTO model_gateway_invocation"), args.capture());
        assertEquals("REJECTED_RATE_LIMITED", args.getValue()[5]);
    }

    @Test void quotaRejectionIsAudited() {
        var principal = new ModelGatewayService.GatewayPrincipal(4L, 9L, "PERSONAL");
        when(jdbc.query(contains("model_gateway_key WHERE id=?"), any(RowMapper.class), eq(4L)))
                .thenReturn(List.of(Map.of("requests", 5L, "tokens", -1L)));
        stubNoGroupLimits();
        stubUsage(6, 0, 1);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> gateway.invoke(principal, "ops", new ModelInvocationRequest()));
        assertEquals(429, failure.getCode());

        org.mockito.ArgumentCaptor<Object[]> args = org.mockito.ArgumentCaptor.forClass(Object[].class);
        verify(jdbc).update(startsWith("INSERT INTO model_gateway_invocation"), args.capture());
        assertEquals("REJECTED_QUOTA", args.getValue()[5]);
    }
}
