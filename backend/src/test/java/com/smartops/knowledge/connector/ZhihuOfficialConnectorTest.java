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

/** 形态 B · 知乎官方 API（独立测试类）：与百度官方形态互不混用。 */
class ZhihuOfficialConnectorTest {

    private final SessionUser actor = new SessionUser(7L, "alice", "user");

    private KnowledgeCrawlService crawlerCapturing(AtomicReference<Map<String, String>> headers, String json) {
        return new KnowledgeCrawlService(new JdbcTemplate(), mock(PersonalKnowledgeService.class)) {
            @Override
            public String fetch(String url, String accept, Map<String, String> extraHeaders) {
                headers.set(extraHeaders);
                assertTrue(url.startsWith("https://zhihu-gw.example.com/search?"), () -> "unexpected " + url);
                return json;
            }
        };
    }

    @Test
    void missingKeyMeansNotConfigured() {
        var crawler = crawlerCapturing(new AtomicReference<>(), "{}");
        assertFalse(new ZhihuOfficialConnector(crawler, true, "", "https://zhihu-gw.example.com/search").isEnabled());
    }

    @Test
    void searchSendsAuthorizationAndParsesItems() throws Exception {
        var headers = new AtomicReference<Map<String, String>>();
        String json = "{\"items\":[{\"title\":\"知乎官方内容\",\"url\":\"https://www.zhihu.com/question/1\",\"snippet\":\"权威\"}]}";
        var connector = new ZhihuOfficialConnector(crawlerCapturing(headers, json), true, "zk", "https://zhihu-gw.example.com/search");

        var results = connector.search(actor, "kubernetes", 8);

        assertEquals("ZHIHU_OFFICIAL", results.get(0).kind());
        assertEquals("Bearer zk", headers.get().get("Authorization"));
    }

    @Test
    void emptyResponseFailsExplicitly() throws Exception {
        var connector = new ZhihuOfficialConnector(
                crawlerCapturing(new AtomicReference<>(), "{\"items\":[]}"), true, "zk", "https://zhihu-gw.example.com/search");
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.search(actor, "kubernetes", 8));
        assertEquals("ZHIHU_OFFICIAL_FAILED", failure.getMessage());
    }
}
