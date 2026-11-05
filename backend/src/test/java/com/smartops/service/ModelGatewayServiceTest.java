package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import java.util.List;
import java.util.Map;

class ModelGatewayServiceTest {
    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final ModelConnectionService connections = mock(ModelConnectionService.class);
    private final ModelGatewayService gateway = new ModelGatewayService(jdbc, connections);

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
        when(jdbc.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class), eq(4L)))
                .thenReturn(List.of(Map.of("requests", -1L, "tokens", -1L)));
        when(jdbc.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class), eq("ops"), eq(9L)))
                .thenAnswer(call -> call.getArgument(0, String.class).contains("request_limit_24h")
                        ? List.<Map<String, Long>>of()
                        : List.of(Map.of("routeId", 101L, "connectionId", 11L), Map.of("routeId", 102L, "connectionId", 12L)));
        when(connections.invoke(eq(9L), eq(11L), any(ModelInvocationRequest.class)))
                .thenThrow(new IllegalStateException("provider down"));
        when(connections.invoke(eq(9L), eq(12L), any(ModelInvocationRequest.class)))
                .thenReturn(ModelInvocationResponse.builder().model("backup").content("ok").usage(Map.of()).build());

        var result = gateway.invoke(principal, "ops", new ModelInvocationRequest());

        assertEquals("ok", result.getContent());
    }

    @Test void groupQuotaStillAppliesWhenKeyHasNoLimit() {
        var principal = new ModelGatewayService.GatewayPrincipal(4L, 9L, "PERSONAL");
        when(jdbc.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class), eq(4L)))
                .thenReturn(List.of(Map.of("requests", -1L, "tokens", -1L)));
        when(jdbc.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class), eq("ops"), eq(9L)))
                .thenReturn(List.of(Map.of("requests", 5L, "tokens", -1L)));
        when(jdbc.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class), eq(9L), eq("ops")))
                .thenReturn(List.of(Map.of("calls", 5L, "tokens", 0L)));

        assertEquals(429, assertThrows(BusinessException.class,
                () -> gateway.invoke(principal, "ops", new ModelInvocationRequest())).getCode());
    }
}
