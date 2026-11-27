package com.smartops.service;

import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class ModelSemanticCacheServiceTest {

    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
    private final ModelSemanticCacheService cache = new ModelSemanticCacheService(jdbc, meterRegistry);

    private void enable() {
        ReflectionTestUtils.setField(cache, "enabled", true);
        ReflectionTestUtils.setField(cache, "ttlMinutes", 60);
        ReflectionTestUtils.setField(cache, "similarityThreshold", 0.85);
        ReflectionTestUtils.setField(cache, "candidateLimit", 50);
    }

    private ModelSemanticCacheService.CacheRow row(String digest, String content) {
        return new ModelSemanticCacheService.CacheRow(1L, "ollama", "deepseek-r1:8b", content,
                10, 20, 30, digest);
    }

    @Test
    void disabledCacheSkipsDatabaseEntirely() {
        ReflectionTestUtils.setField(cache, "enabled", false);
        var request = new ModelInvocationRequest();
        request.setPrompt("check server status");

        assertTrue(cache.lookup(1L, "ops", request).isEmpty());
        cache.store(1L, "ops", request, ModelInvocationResponse.builder().content("ok").build());
        verifyNoInteractions(jdbc);
    }

    @Test
    void exactHashHitReturnsCachedResponse() {
        enable();
        var request = new ModelInvocationRequest();
        request.setPrompt("查询服务器状态");
        request.setSystemPrompt("你是运维助手");
        request.setTemperature(0.2);
        when(jdbc.query(contains("exact_hash"), any(RowMapper.class), anyString()))
                .thenReturn(List.of(row("查询服务器状态", "服务器正常")));

        var hit = cache.lookup(1L, "ops", request);

        assertTrue(hit.isPresent());
        assertEquals("服务器正常", hit.get().getContent());
        assertEquals("deepseek-r1:8b", hit.get().getModel());
        verify(jdbc).update(contains("hit_count=hit_count+1"), any(Object[].class));
    }

    @Test
    void rephrasedPromptHitsViaBigramSimilarity() {
        enable();
        var request = new ModelInvocationRequest();
        request.setPrompt("查询一下服务器的状态。");   // 与缓存摘要只差标点
        when(jdbc.query(contains("exact_hash"), any(RowMapper.class), anyString()))
                .thenReturn(List.of());
        when(jdbc.query(contains("semantic_hash"), any(RowMapper.class), anyString(), anyString()))
                .thenReturn(List.of(row("查询一下服务器的状态", "服务器正常")));

        var hit = cache.lookup(1L, "ops", request);

        assertTrue(hit.isPresent());
        assertEquals("服务器正常", hit.get().getContent());
    }

    @Test
    void dissimilarPromptMissesCache() {
        enable();
        var request = new ModelInvocationRequest();
        request.setPrompt("帮我部署一个全新的 kubernetes 集群");
        when(jdbc.query(contains("exact_hash"), any(RowMapper.class), anyString()))
                .thenReturn(List.of());
        when(jdbc.query(contains("semantic_hash"), any(RowMapper.class), anyString(), anyString()))
                .thenReturn(List.of(row("查询服务器状态", "服务器正常")));

        assertTrue(cache.lookup(1L, "ops", request).isEmpty());
    }

    @Test
    void emptyPromptIsNeverCached() {
        enable();
        var request = new ModelInvocationRequest();
        request.setPrompt("   !!!。");   // 归一化后为空

        assertTrue(cache.lookup(1L, "ops", request).isEmpty());
        cache.store(1L, "ops", request, ModelInvocationResponse.builder().content("ok").build());
        verify(jdbc, never()).update(contains("INSERT INTO model_semantic_cache"), any(Object[].class));
    }

    @Test
    void failedProviderResponseIsNotStored() {
        enable();
        var request = new ModelInvocationRequest();
        request.setPrompt("check status");
        // 空内容不写缓存
        cache.store(1L, "ops", request, ModelInvocationResponse.builder().content("").build());
        verify(jdbc, never()).update(anyString(), any(Object[].class));
        verify(jdbc, never()).update(anyString());
    }

    @Test
    void normalizeStripsPunctuationAndCase() {
        // 标点/空白统一折叠为单个空格，避免相邻词粘连
        assertEquals("查询 服务器 状态", ModelSemanticCacheService.normalize("查询！ 服务器、状态？？"));
        assertEquals("check server status", ModelSemanticCacheService.normalize("Check, SERVER  Status!"));
        assertTrue(ModelSemanticCacheService.normalize(null).isEmpty());
    }

    @Test
    void bigramJaccardScoresRephrasing() {
        assertEquals(1.0, ModelSemanticCacheService.bigramJaccard("查询状态", "查询状态"));
        assertTrue(ModelSemanticCacheService.bigramJaccard("查询服务器状态", "查询服务器的状态！") > 0.5);
        assertTrue(ModelSemanticCacheService.bigramJaccard("查询状态", "部署集群") < 0.3);
        // 单字符 Jaccard 对中文插入字更稳（"的"插入 → 0.875）
        assertTrue(ModelSemanticCacheService.charJaccard("查询服务器状态", "查询服务器的状态") > 0.85);
        assertTrue(ModelSemanticCacheService.charJaccard("查询状态", "部署集群") < 0.3);
    }

    @Test
    void storeWritesRowAndCleansExpiredEntries() {
        enable();
        var request = new ModelInvocationRequest();
        request.setPrompt("check status");
        var result = ModelInvocationResponse.builder()
                .provider("ollama").model("deepseek-r1:8b").content("ok")
                .usage(Map.of("prompt_tokens", 10, "completion_tokens", 20, "total_tokens", 30))
                .build();

        cache.store(1L, "ops", request, result);

        verify(jdbc).update(contains("DELETE FROM model_semantic_cache WHERE exact_hash"), anyString());
        verify(jdbc).update(contains("INSERT INTO model_semantic_cache"), any(Object[].class));
        verify(jdbc).update(contains("created_at < DATE_SUB"), eq("ops"));
    }

    @Test
    void gatewayMarksCacheHitAndSkipsRoutes() {
        var jdbc = mock(JdbcTemplate.class);
        var connections = mock(ModelConnectionService.class);
        var cache = mock(ModelSemanticCacheService.class);
        var router = mock(ModelRouterService.class);
        var gateway = new ModelGatewayService(jdbc, connections, cache, router,
                mock(com.smartops.service.modelconfig.ModelConfigRegistry.class), 60L);
        var principal = new ModelGatewayService.GatewayPrincipal(4L, 9L, "PERSONAL");
        var request = new ModelInvocationRequest();
        request.setPrompt("same question");
        // 配额上下文：key 限额未配置（-1），模型组无限额配置 → 跳过配额校验
        when(jdbc.query(contains("model_gateway_key WHERE id=?"), any(RowMapper.class), eq(4L)))
                .thenReturn(List.of(Map.of("requests", -1L, "tokens", -1L)));
        when(jdbc.query(contains("model_gateway_group WHERE slug=?"), any(RowMapper.class), eq("ops"), eq(9L)))
                .thenReturn(List.of());
        when(cache.lookup(eq(4L), eq("ops"), eq(request)))
                .thenReturn(Optional.of(ModelInvocationResponse.builder().model("deepseek-r1:8b").content("cached!").usage(Map.of()).build()));

        var result = gateway.invoke(principal, "ops", request);

        assertEquals("cached!", result.getContent());
        assertEquals(Boolean.TRUE, result.getCached());
        verifyNoInteractions(connections);
        verify(jdbc, never()).query(contains("model_gateway_route"), any(RowMapper.class), anyString(), any());
    }
}
