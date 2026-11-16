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

/** 形态 C · 指定 URL 读取 · 知乎域（独立测试类）：与百度 URL 形态互不混用。 */
class ZhihuUrlConnectorTest {

    private final SessionUser actor = new SessionUser(7L, "alice", "user");

    private static WebResearchService.WebPage page(String url) {
        return new WebResearchService.WebPage(2L, url, url, "zhuanlan.zhihu.com", "专栏", "摘要", "正文",
                "hash", Instant.EPOCH, "JS", "JS 渲染 · 匿名会话");
    }

    @Test
    void nonZhihuUrlIsRejected() {
        var connector = new ZhihuUrlConnector(mock(WebRenderService.class), true);
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.fetch(actor, "https://example.com/question/1"));
        assertEquals("ZHIHU_URL_REJECTED", failure.getMessage());
    }

    @Test
    void zhihuUrlDelegatesToControlledRender() {
        var renderService = mock(WebRenderService.class);
        when(renderService.fetchRendered(eq(actor), eq("https://zhuanlan.zhihu.com/p/1")))
                .thenReturn(page("https://zhuanlan.zhihu.com/p/1"));
        var connector = new ZhihuUrlConnector(renderService, true);

        var result = connector.fetch(actor, "https://zhuanlan.zhihu.com/p/1");

        assertEquals("JS", result.renderMode());
        assertEquals("zhuanlan.zhihu.com", result.site());
    }

    @Test
    void unreadablePageFailsWithExplicitCode() {
        var renderService = mock(WebRenderService.class);
        when(renderService.fetchRendered(any(SessionUser.class), any()))
                .thenThrow(new BusinessException(422, "WEB_RESEARCH_EMPTY_CONTENT"));
        var connector = new ZhihuUrlConnector(renderService, true);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.fetch(actor, "https://zhuanlan.zhihu.com/p/1"));
        assertEquals("ZHIHU_URL_UNREADABLE", failure.getMessage());
    }

    @Test
    void hostValidationCoversZhihuFamilyOnly() {
        assertTrue(ZhihuUrlConnector.isZhihuUrl("https://www.zhihu.com/question/1"));
        assertTrue(ZhihuUrlConnector.isZhihuUrl("https://zhuanlan.zhihu.com/p/1"));
        assertFalse(ZhihuUrlConnector.isZhihuUrl("https://evil.com/zhihu.com"));
        assertFalse(ZhihuUrlConnector.isZhihuUrl("https://baidu.com"));
    }
}
