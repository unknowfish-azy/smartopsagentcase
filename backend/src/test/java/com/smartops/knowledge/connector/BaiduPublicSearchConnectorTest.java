package com.smartops.knowledge.connector;

import com.smartops.exception.BusinessException;
import com.smartops.knowledge.KnowledgeCrawlService;
import com.smartops.security.SessionUser;
import com.smartops.service.PersonalKnowledgeService;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

/** 形态 A · 百度公开页（独立测试类）：风控如实标注 + 公开结果解析。 */
class BaiduPublicSearchConnectorTest {

    private final SessionUser actor = new SessionUser(7L, "alice", "user");

    private KnowledgeCrawlService crawlerReturning(String html) {
        return new KnowledgeCrawlService(new JdbcTemplate(), mock(PersonalKnowledgeService.class)) {
            @Override
            public String fetch(String url, String accept) {
                assertTrue(url.startsWith("https://www.baidu.com/s?wd="), () -> "unexpected " + url);
                return html;
            }
        };
    }

    @Test
    void challengePageIsReportedHonestlyNotBypassed() {
        var connector = new BaiduPublicSearchConnector(
                crawlerReturning("<html><title>百度安全验证</title></html>"), true);
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.search(actor, "kubernetes", 8));
        assertEquals("BAIDU_CHALLENGE_REQUIRED", failure.getMessage());
    }

    @Test
    void parsesPublicResultPageWithKindLabel() throws Exception {
        String html = "<h3 class=\"t\"><a href=\"http://www.baidu.com/link?url=abc\">K8s 指南</a></h3>"
                + "<div class=\"c-abstract\">内容摘要一</div>"
                + "<h3 class=\"t\"><a href=\"http://www.baidu.com/link?url=def\">运维手册</a></h3>";
        var connector = new BaiduPublicSearchConnector(crawlerReturning(html), true);
        var results = connector.search(actor, "kubernetes", 8);
        assertEquals(2, results.size());
        assertEquals("BAIDU_PUBLIC", results.get(0).kind());
        assertEquals("K8s 指南", results.get(0).title());
        assertEquals("内容摘要一", results.get(0).snippet());
    }

    @Test
    void emptyPageFailsWithExplicitCode() throws Exception {
        var connector = new BaiduPublicSearchConnector(crawlerReturning("<html><body>nothing</body></html>"), true);
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.search(actor, "kubernetes", 8));
        assertEquals("BAIDU_PUBLIC_FAILED", failure.getMessage());
    }

    @Test
    void disabledByDefault() {
        assertFalse(new BaiduPublicSearchConnector(crawlerReturning(""), false).isEnabled());
    }
}
