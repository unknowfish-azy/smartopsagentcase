package com.smartops.knowledge;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;

/** T41：雷达抓取的 JS 渲染降级——SPA 骨架正文过短时走受控渲染，失败如实回退。 */
class KnowledgeCrawlJsRenderFallbackTest {

    private final WebResearchMetrics metrics = mock(WebResearchMetrics.class);

    private KnowledgeCrawlService service(HeadlessRenderer renderer) {
        return new KnowledgeCrawlService(new JdbcTemplate(), mock(com.smartops.service.PersonalKnowledgeService.class),
                mock(com.smartops.service.KnowledgeCandidateService.class), metrics, renderer);
    }

    private HeadlessRenderer availableRenderer(String text) {
        HeadlessRenderer renderer = mock(HeadlessRenderer.class);
        when(renderer.isAvailable()).thenReturn(true);
        when(renderer.render(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.nullable(String.class)))
                .thenReturn(new HeadlessRenderer.RenderedPage("title", text));
        return renderer;
    }

    @Test
    void longStaticTextSkipsRendering() {
        HeadlessRenderer renderer = availableRenderer("rendered body");
        String longText = "x".repeat(300);
        assertEquals(longText, service(renderer).tryJsRenderFallback("https://docs.example.com/guide", longText, "static title").text());
        verify(renderer, never()).render(anyString(), anyString());
    }

    @Test
    void shortStaticTextFallsBackToRenderedBody() {
        HeadlessRenderer renderer = availableRenderer("完整的 SPA 正文，长度超过静态骨架。".repeat(20));
        KnowledgeCrawlService.FallbackPage result = service(renderer).tryJsRenderFallback("https://docs.example.com/guide", "Loading...", "static title");
        assertEquals("完整的 SPA 正文，长度超过静态骨架。".repeat(20), result.text());
        // 标题跟随渲染结果（渲染 title 非空时），避免 SPA 页面停留在骨架通用站名。
        assertEquals("title", result.title());
        verify(metrics).radarJsFallback();
    }

    @Test
    void shorterRenderedBodyKeepsStaticText() {
        // 渲染只拿到弹窗文本时不得覆盖静态正文：取更长一方，防止误伤。
        HeadlessRenderer renderer = availableRenderer("cookie");
        String staticText = "static".repeat(20);
        assertEquals(staticText, service(renderer).tryJsRenderFallback("https://docs.example.com/guide", staticText, "static title").text());
        verify(metrics).radarJsFallback();
    }

    @Test
    void unavailableRendererKeepsStaticTextHonestly() {
        HeadlessRenderer renderer = mock(HeadlessRenderer.class);
        when(renderer.isAvailable()).thenReturn(false);
        assertEquals("", service(renderer).tryJsRenderFallback("https://docs.example.com/guide", "", "static title").text());
        verify(renderer, never()).render(anyString(), anyString());
    }

    @Test
    void renderFailureFallsBackToStaticTextWithoutFabrication() {
        HeadlessRenderer renderer = mock(HeadlessRenderer.class);
        when(renderer.isAvailable()).thenReturn(true);
        when(renderer.render(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.nullable(String.class)))
                .thenThrow(new com.smartops.exception.BusinessException(503, "RENDER_TIMEOUT"));
        assertEquals("", service(renderer).tryJsRenderFallback("https://docs.example.com/guide", "", "static title").text());
        verify(metrics, never()).radarJsFallback();
    }
}
