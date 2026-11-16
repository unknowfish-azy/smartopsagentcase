package com.smartops.knowledge.connector;

import com.smartops.exception.BusinessException;
import com.smartops.knowledge.KnowledgeCrawlService;
import com.smartops.knowledge.WebResearchService;
import com.smartops.security.SessionUser;
import com.smartops.service.PersonalKnowledgeService;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

/** T34a：连接器聚合、既有 DDG/GITHUB 迁移行为等价、形态互不 fallback、scope 校验。 */
class WebResearchConnectorAggregationTest {

    private final SessionUser actor = new SessionUser(7L, "alice", "user");

    private static final String DDG_HTML = "<a class='result__a' href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa'>A result</a>"
            + "<a class='result__snippet'>snippet a</a>";

    private KnowledgeCrawlService crawler(String ddgHtml, String githubJson) {
        return new KnowledgeCrawlService(new JdbcTemplate(), mock(PersonalKnowledgeService.class)) {
            @Override
            public String fetch(String url) {
                throw new AssertionError("generic fetch must not be used by search connectors");
            }

            @Override
            public String fetch(String url, String accept) {
                if (url.contains("duckduckgo.com")) {
                    if (ddgHtml == null) throw new RuntimeException("ddg down");
                    return ddgHtml;
                }
                if (url.contains("api.github.com")) {
                    if (githubJson == null) throw new RuntimeException("github down");
                    return githubJson;
                }
                if (url.contains("baidu.com")) {
                    return "<html><title>百度安全验证</title></html>";
                }
                if (url.contains("zhihu.com")) {
                    return "<html>系统监测到您的网络环境存在异常</html>";
                }
                throw new RuntimeException("unexpected " + url);
            }
        };
    }

    private static JdbcTemplate taskJdbc() {
        var jdbc = new JdbcTemplate(new org.springframework.jdbc.datasource.DriverManagerDataSource(
                "jdbc:h2:mem:wr-aggr-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        jdbc.execute("CREATE TABLE web_research_task (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, task_type VARCHAR(32) NOT NULL, query_text CLOB NOT NULL, result_count INT NOT NULL DEFAULT 0, status VARCHAR(32) NOT NULL, error_code VARCHAR(500), created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMP NULL)");
        return jdbc;
    }

    @Test
    void migratedDuckDuckGoConnectorMatchesLegacyParse() throws Exception {
        DuckDuckGoConnector connector = new DuckDuckGoConnector(crawler(DDG_HTML, null), true);
        var results = connector.search(actor, "query", 8);
        var legacy = WebResearchService.parseWebResults(DDG_HTML, 8);
        // 迁移行为等价：除 kind 重标为形态标识 DDG 外，其余字段与旧 WEB 分支完全一致
        assertEquals(legacy.size(), results.size());
        for (int i = 0; i < legacy.size(); i++) {
            assertEquals(legacy.get(i).title(), results.get(i).title());
            assertEquals(legacy.get(i).url(), results.get(i).url());
            assertEquals(legacy.get(i).site(), results.get(i).site());
            assertEquals(legacy.get(i).snippet(), results.get(i).snippet());
            assertEquals("DDG", results.get(i).kind());
        }
    }

    @Test
    void migratedGithubConnectorMatchesLegacyParse() throws Exception {
        String json = "{\"items\":[{\"full_name\":\"smartops/agent\",\"html_url\":\"https://github.com/smartops/agent\",\"description\":\"d\"}]}";
        GithubConnector connector = new GithubConnector(crawler(null, json), true);
        var results = connector.search(actor, "query", 8);
        var legacy = WebResearchService.parseGithubResults(json, 8);
        // retrievedAt 为即时时间戳，不参与比较
        assertEquals(legacy.size(), results.size());
        for (int i = 0; i < legacy.size(); i++) {
            assertEquals(legacy.get(i).title(), results.get(i).title());
            assertEquals(legacy.get(i).url(), results.get(i).url());
            assertEquals(legacy.get(i).kind(), results.get(i).kind());
        }
    }

    @Test
    void aggregationMergesEnabledConnectorsAndLabelsKind() {
        var jdbc = taskJdbc();
        var crawler = crawler(DDG_HTML,
                "{\"items\":[{\"full_name\":\"smartops/agent\",\"html_url\":\"https://github.com/smartops/agent\",\"description\":\"d\"}]}");
        var service = new WebResearchService(crawler, jdbc, new com.fasterxml.jackson.databind.ObjectMapper(),
                List.of(new DuckDuckGoConnector(crawler, true), new GithubConnector(crawler, true)));

        var response = service.search(actor, "kubernetes", "ALL", 8);

        assertEquals("SUCCESS", response.status());
        assertEquals(List.of("DDG", "GITHUB"), response.results().stream().map(r -> r.kind()).toList());
    }

    @Test
    void partialFailureKeepsOtherConnectorResultsAndRecordsError() {
        var jdbc = taskJdbc();
        var crawler = crawler(DDG_HTML, null);
        var service = new WebResearchService(crawler, jdbc, new com.fasterxml.jackson.databind.ObjectMapper(),
                List.of(new DuckDuckGoConnector(crawler, true), new GithubConnector(crawler, true)));

        var response = service.search(actor, "kubernetes", "ALL", 8);

        assertEquals("PARTIAL", response.status());
        assertEquals(1, response.results().size());
        assertTrue(response.errors().get(0).startsWith("GITHUB:"));
    }

    @Test
    void disabledConnectorIsSkippedWithoutNetwork() {
        var jdbc = taskJdbc();
        var crawler = crawler(DDG_HTML, null);
        var service = new WebResearchService(crawler, jdbc, new com.fasterxml.jackson.databind.ObjectMapper(),
                List.of(new DuckDuckGoConnector(crawler, false), new GithubConnector(crawler, false)));

        var response = service.search(actor, "kubernetes", "ALL", 8);

        // 全禁用 = 不出网、无结果、无错误（不伪造失败也不伪造结果）
        assertTrue(response.results().isEmpty());
        assertTrue(response.errors().isEmpty());
    }

    @Test
    void formsDoNotFallbackOnEachOther() {
        var jdbc = taskJdbc();
        // A 形态（百度公开页）被风控拦截；B 形态无凭证未启用 —— 失败绝不互相切换
        var crawler = crawler(null, null);
        var baiduPublic = new BaiduPublicSearchConnector(crawler, true);
        var baiduOfficial = new BaiduOfficialConnector(crawler, true, "", "");
        var service = new WebResearchService(crawler, jdbc, new com.fasterxml.jackson.databind.ObjectMapper(),
                List.of(baiduPublic, baiduOfficial));

        var response = service.search(actor, "kubernetes", "ALL", 8);

        assertEquals("FAILED", response.status());
        assertTrue(response.errors().stream().anyMatch(error -> error.startsWith("BAIDU_PUBLIC:BAIDU_CHALLENGE_REQUIRED")));
        assertTrue(response.errors().stream().noneMatch(error -> error.contains("OFFICIAL")));
        assertFalse(baiduOfficial.isEnabled());
    }

    @Test
    void scopeAcceptsConnectorIdsAndRejectsUnknown() {
        var jdbc = taskJdbc();
        var crawler = crawler(DDG_HTML, null);
        var service = new WebResearchService(crawler, jdbc, new com.fasterxml.jackson.databind.ObjectMapper(),
                List.of(new DuckDuckGoConnector(crawler, true)));
        assertEquals("SUCCESS", service.search(actor, "q", "DDG", 8).status());
        assertEquals("SUCCESS", service.search(actor, "q", "WEB", 8).status());
        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.search(actor, "q", "WEIBO", 8));
        assertEquals("WEB_RESEARCH_SCOPE_INVALID", failure.getMessage());
    }
}
