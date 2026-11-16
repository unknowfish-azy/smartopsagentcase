package com.smartops.knowledge.connector;

import com.smartops.exception.BusinessException;
import com.smartops.knowledge.KnowledgeCrawlService;
import com.smartops.security.SessionUser;
import com.smartops.service.PersonalKnowledgeService;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

/** 形态 A · 知乎公开页（独立测试类）：登录墙如实标注 + 公开结果解析。 */
class ZhihuPublicSearchConnectorTest {

    private final SessionUser actor = new SessionUser(7L, "alice", "user");

    private KnowledgeCrawlService crawlerReturning(String html) {
        return new KnowledgeCrawlService(new JdbcTemplate(), mock(PersonalKnowledgeService.class)) {
            @Override
            public String fetch(String url, String accept) {
                assertTrue(url.startsWith("https://www.zhihu.com/search?"), () -> "unexpected " + url);
                return html;
            }
        };
    }

    @Test
    void loginWallIsReportedHonestlyNotBypassed() {
        var connector = new ZhihuPublicSearchConnector(
                crawlerReturning("<html>系统监测到您的网络环境存在异常，请验证</html>"), true);
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.search(actor, "kubernetes", 8));
        assertEquals("ZHIHU_CHALLENGE_REQUIRED", failure.getMessage());
    }

    @Test
    void parsesPublicQuestionAndArticleLinks() throws Exception {
        String html = "<a href=\"/question/12345\">如何排查 K8s 网络问题？</a>"
                + "<a href=\"https://zhuanlan.zhihu.com/p/67890\">运维复盘指南</a>";
        var connector = new ZhihuPublicSearchConnector(crawlerReturning(html), true);
        var results = connector.search(actor, "kubernetes", 8);
        assertEquals(2, results.size());
        assertEquals("ZHIHU_PUBLIC", results.get(0).kind());
        assertEquals("https://www.zhihu.com/question/12345", results.get(0).url());
        assertEquals("https://zhuanlan.zhihu.com/p/67890", results.get(1).url());
    }

    @Test
    void emptyPageFailsWithExplicitCode() throws Exception {
        var connector = new ZhihuPublicSearchConnector(crawlerReturning("<html><body>ok</body></html>"), true);
        BusinessException failure = assertThrows(BusinessException.class,
                () -> connector.search(actor, "kubernetes", 8));
        assertEquals("ZHIHU_PUBLIC_FAILED", failure.getMessage());
    }

    @Test
    void disabledByDefault() {
        assertFalse(new ZhihuPublicSearchConnector(crawlerReturning(""), false).isEnabled());
    }
}
