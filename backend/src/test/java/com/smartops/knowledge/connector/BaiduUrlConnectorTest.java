package com.smartops.knowledge.connector;

import com.smartops.exception.BusinessException;
import com.smartops.knowledge.WebRenderService;
import com.smartops.knowledge.WebResearchService;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/** 形态 C · 指定 URL 读取 · 百度域（独立测试类）：域校验 + 委托受控渲染 + 不可读如实标注。 */
class BaiduUrlConnectorTest {

    private final SessionUser actor = new SessionUser(7L, "alice", "user");

    private static WebResearchService.WebPage page(String url) {
        return new WebResearchService.WebPage(1L, url, url, "baijiahao.baidu.com", "标题", "摘要", "正文",
                "hash", Instant.EPOCH, "JS", "JS 渲染 · 匿名会话");
    }

    @Test
    void nonBaiduUrlIsRejectedBeforeRender() {
        var renderService = mock(WebRenderService.class);
        var connector = new BaiduUrlConnector(renderService, true);
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.fetch(actor, "https://example.com/page"));
        assertEquals("BAIDU_URL_REJECTED", failure.getMessage());
    }

    @Test
    void baiduUrlDelegatesToControlledRender() {
        var renderService = mock(WebRenderService.class);
        when(renderService.fetchRendered(eq(actor), eq("https://baijiahao.baidu.com/s?id=1")))
                .thenReturn(page("https://baijiahao.baidu.com/s?id=1"));
        var connector = new BaiduUrlConnector(renderService, true);

        var result = connector.fetch(actor, "https://baijiahao.baidu.com/s?id=1");

        assertEquals("JS", result.renderMode());
    }

    @Test
    void unreadablePageFailsWithExplicitCode() {
        var renderService = mock(WebRenderService.class);
        when(renderService.fetchRendered(any(SessionUser.class), any()))
                .thenThrow(new BusinessException(502, "WEB_RESEARCH_RENDER_FAILED"));
        var connector = new BaiduUrlConnector(renderService, true);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.fetch(actor, "https://baijiahao.baidu.com/s?id=1"));
        assertEquals("BAIDU_URL_UNREADABLE", failure.getMessage());
    }

    @Test
    void doesNotParticipateInSearch() {
        var connector = new BaiduUrlConnector(mock(WebRenderService.class), true);
        assertFalse(connector.supportsSearch());
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.search(actor, "q", 8));
        assertEquals("CONNECTOR_SEARCH_UNSUPPORTED", failure.getMessage());
    }

    @Test
    void hostValidationCoversBaiduFamilyOnly() {
        assertTrue(BaiduUrlConnector.isBaiduUrl("https://www.baidu.com/s?wd=x"));
        assertTrue(BaiduUrlConnector.isBaiduUrl("https://baijiahao.baidu.com/s?id=1"));
        assertFalse(BaiduUrlConnector.isBaiduUrl("https://evil.com/baidu.com"));
        assertFalse(BaiduUrlConnector.isBaiduUrl("not-a-url"));
    }
}
