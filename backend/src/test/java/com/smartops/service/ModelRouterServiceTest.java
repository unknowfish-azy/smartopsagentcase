package com.smartops.service;

import com.smartops.dto.model.ModelInvocationRequest;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;

class ModelRouterServiceTest {

    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final ModelRouterService router = new ModelRouterService(jdbc);

    private ModelInvocationRequest request(String prompt) {
        var r = new ModelInvocationRequest();
        r.setPrompt(prompt);
        return r;
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private void stubGroupMode(String slug, Long ownerUserId, String mode, String defaultCap) {
        var m = new java.util.HashMap<String, String>();
        m.put("mode", mode);
        m.put("defaultCapability", defaultCap);
        doReturn(List.of(m))
                .when(jdbc).query(ArgumentMatchers.contains("model_gateway_group WHERE slug=?"),
                        ArgumentMatchers.any(org.springframework.jdbc.core.RowMapper.class),
                        eq(slug), eq(ownerUserId));
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private void stubAutoConnsEmpty(Long ownerUserId) {
        // AUTO 能力查询（SELECT id,name,model_name,capabilities ...）返回空 → 触发降级链
        doReturn(List.of())
                .when(jdbc).query(ArgumentMatchers.contains("capabilities FROM model_connections"),
                        ArgumentMatchers.any(org.springframework.jdbc.core.RowMapper.class),
                        eq(ownerUserId));
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private void stubFallbackConnection(Long ownerUserId, List<ModelRouterService.RoutedConnection> rows) {
        // 最终兜底直查（SELECT id ... LIMIT 1）
        doReturn(rows)
                .when(jdbc).query(ArgumentMatchers.contains("ORDER BY id ASC LIMIT 1"),
                        ArgumentMatchers.any(org.springframework.jdbc.core.RowMapper.class),
                        eq(ownerUserId));
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private void stubConns(Long ownerUserId, List<Object[]> conns) {
        doReturn(conns).when(jdbc).query(ArgumentMatchers.contains("capabilities FROM model_connections"),
                ArgumentMatchers.any(org.springframework.jdbc.core.RowMapper.class),
                eq(ownerUserId));
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private void stubManualRoutes(String groupSlug, Long ownerUserId, List<ModelRouterService.RoutedConnection> routes) {
        doReturn(routes).when(jdbc).query(ArgumentMatchers.contains("model_gateway_route"),
                ArgumentMatchers.any(org.springframework.jdbc.core.RowMapper.class),
                eq(groupSlug), eq(ownerUserId));
    }

    @Test
    void autoRouteVisionPromptMatchesVisionCapableConnection() {
        stubGroupMode("ops", 9L, "AUTO", null);
        stubConns(9L, List.of(
                new Object[]{1L, "m", List.of("chat", "fast", "cheap")},
                new Object[]{6L, "deepseek-v4-pro", List.of("chat", "reasoning", "vision", "tool-calling")}
        ));

        var routes = router.selectConnections("ops", 9L, request("帮我看一下这张截图里有什么问题"));

        assertFalse(routes.isEmpty());
        assertEquals(6L, routes.get(0).connectionId());
        assertTrue(routes.get(0).score() > routes.get(1).score());
    }

    @Test
    void autoRouteReasoningPromptMatchesReasoningConnection() {
        stubGroupMode("diag", 9L, "AUTO", null);
        stubConns(9L, List.of(
                new Object[]{1L, "m", List.of("chat", "fast", "cheap")},
                new Object[]{6L, "deepseek-v4-pro", List.of("chat", "reasoning", "vision", "tool-calling")}
        ));

        var routes = router.selectConnections("diag", 9L, request("请帮我诊断一下这个故障的根因"));

        assertEquals(6L, routes.get(0).connectionId());
    }

    @Test
    void autoRouteFastPromptMayPreferCheapConnection() {
        stubGroupMode("quick", 9L, "AUTO", null);
        stubConns(9L, List.of(
                new Object[]{1L, "m", List.of("chat", "fast", "cheap")},
                new Object[]{6L, "deepseek-v4-pro", List.of("chat", "reasoning", "vision", "tool-calling")}
        ));

        var routes = router.selectConnections("quick", 9L, request("简单说一下服务器状态怎么样"));

        assertEquals(1L, routes.get(0).connectionId());
    }

    @Test
    void manualRouteUsesRouteTable() {
        stubGroupMode("ops", 9L, "MANUAL", null);
        stubManualRoutes("ops", 9L,
                List.of(new ModelRouterService.RoutedConnection(6L, 42L, "MANUAL route", 1.0)));

        var routes = router.selectConnections("ops", 9L, request("anything"));

        assertEquals(1, routes.size());
        assertEquals(6L, routes.get(0).connectionId());
        assertEquals(42L, routes.get(0).routeId());
    }

    @Test
    void autoFallsBackToManualThenFallbackConnection() {
        stubGroupMode("ghost", 9L, "AUTO", null);
        stubAutoConnsEmpty(9L);
        stubManualRoutes("ghost", 9L, List.of());
        stubFallbackConnection(9L, List.of(new ModelRouterService.RoutedConnection(1L, null, "FALLBACK default", 0.5)));

        var routes = router.selectConnections("ghost", 9L, request("anything"));

        assertEquals(1, routes.size());
        assertEquals(1L, routes.get(0).connectionId());
    }

    @Test
    void temperatureHighTriggersReasoningSignal() {
        stubGroupMode("diag", 9L, "AUTO", null);
        stubConns(9L, List.of(
                new Object[]{1L, "m", List.of("chat", "fast")},
                new Object[]{6L, "deepseek-v4-pro", List.of("chat", "reasoning")}
        ));
        var req = request("tell me");
        req.setTemperature(0.9);

        var routes = router.selectConnections("diag", 9L, req);

        assertEquals(6L, routes.get(0).connectionId());
    }

    @Test
    void allUnavailableReturnsEmpty() {
        stubGroupMode("ghost", 9L, "AUTO", null);
        stubConns(9L, List.of());
        stubManualRoutes("ghost", 9L, List.of());

        assertTrue(router.selectConnections("ghost", 9L, request("hi")).isEmpty());
    }
}
