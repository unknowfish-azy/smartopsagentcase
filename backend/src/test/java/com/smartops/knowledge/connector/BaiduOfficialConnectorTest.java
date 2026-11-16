package com.smartops.knowledge.connector;

import com.smartops.exception.BusinessException;
import com.smartops.knowledge.KnowledgeCrawlService;
import com.smartops.security.SessionUser;
import com.smartops.service.PersonalKnowledgeService;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

/** 形态 B · 百度官方 API（独立测试类）：凭证齐备才启用、Authorization 走共享安全链、失败不回退。 */
class BaiduOfficialConnectorTest {

    private final SessionUser actor = new SessionUser(7L, "alice", "user");

    private KnowledgeCrawlService crawlerCapturing(AtomicReference<Map<String, String>> headers, String json) {
        return new KnowledgeCrawlService(new JdbcTemplate(), mock(PersonalKnowledgeService.class)) {
            @Override
            public String fetch(String url, String accept, Map<String, String> extraHeaders) {
                headers.set(extraHeaders);
                assertTrue(url.startsWith("https://official.example.com/search?"), () -> "unexpected " + url);
                return json;
            }
        };
    }

    @Test
    void missingKeyOrEndpointMeansNotConfigured() {
        var crawler = crawlerCapturing(new AtomicReference<>(), "{}");
        assertFalse(new BaiduOfficialConnector(crawler, false, "key", "https://official.example.com/search").isEnabled());
        assertFalse(new BaiduOfficialConnector(crawler, true, "", "https://official.example.com/search").isEnabled());
        assertFalse(new BaiduOfficialConnector(crawler, true, "key", "").isEnabled());
    }

    @Test
    void searchSendsAuthorizationThroughSharedChainAndParsesItems() throws Exception {
        var headers = new AtomicReference<Map<String, String>>();
        String json = "{\"items\":[{\"title\":\"官方指南\",\"url\":\"https://example.com/g\",\"snippet\":\"权威内容\",\"publishedAt\":\"2026-11-01\"}]}";
        var connector = new BaiduOfficialConnector(crawlerCapturing(headers, json), true, "secret-key", "https://official.example.com/search");

        var results = connector.search(actor, "kubernetes", 8);

        assertEquals("BAIDU_OFFICIAL", results.get(0).kind());
        assertEquals("官方指南", results.get(0).title());
        assertEquals("Bearer secret-key", headers.get().get("Authorization"));
    }

    @Test
    void malformedResponseFailsExplicitlyWithoutFallback() throws Exception {
        var connector = new BaiduOfficialConnector(
                crawlerCapturing(new AtomicReference<>(), "{\"items\":[]}"), true, "secret-key", "https://official.example.com/search");
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.search(actor, "kubernetes", 8));
        assertEquals("BAIDU_OFFICIAL_FAILED", failure.getMessage());
    }

    @Test
    void fetchIsUnsupported() {
        var connector = new BaiduOfficialConnector(
                crawlerCapturing(new AtomicReference<>(), "{}"), true, "secret-key", "https://official.example.com/search");
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.fetch(actor, "https://example.com/page"));
        assertEquals("CONNECTOR_FETCH_UNSUPPORTED", failure.getMessage());
    }
}
