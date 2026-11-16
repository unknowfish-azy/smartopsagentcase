package com.smartops.knowledge;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.service.PersonalKnowledgeService;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

class WebResearchServiceTest {
    private final SessionUser actor = new SessionUser(1L, "alice", "user");

    @Test
    void parsesPublicSearchResultAndDecodesTarget() {
        String html = "<a class='result__a' href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fguide%3Fa%3D1'>Example <b>Guide</b></a>"
                + "<a class='result__snippet'>A <b>safe</b> operations guide</a>";

        List<WebResearchService.SearchResult> results = WebResearchService.parseWebResults(html, 8);

        assertEquals(1, results.size());
        assertEquals("https://example.com/guide?a=1", results.get(0).url());
        assertEquals("example.com", results.get(0).site());
        assertEquals("Example Guide", results.get(0).title());
        assertTrue(results.get(0).snippet().contains("safe"));
    }

    @Test
    void dropsNonPublicSearchTargets() {
        String html = "<a class='result__a' href='http://127.0.0.1:8080/internal'>internal</a>";
        assertTrue(WebResearchService.parseWebResults(html, 8).isEmpty());
    }

    @Test
    void parsesGithubRepositoryEvidence() throws Exception {
        String json = "{\"items\":[{\"full_name\":\"smartops/agent\",\"html_url\":\"https://github.com/smartops/agent\","
                + "\"description\":\"Operations knowledge\",\"updated_at\":\"2026-11-15T00:00:00Z\"}]}";

        List<WebResearchService.SearchResult> results = WebResearchService.parseGithubResults(json, 8);

        assertEquals(1, results.size());
        assertEquals("smartops/agent", results.get(0).title());
        assertEquals("GITHUB", results.get(0).kind());
        assertEquals("2026-11-15T00:00:00Z", results.get(0).publishedAt());
    }

    @Test
    void fetchStoresServerSideSnapshotAndReturnsTaskId() {
        var jdbc = researchJdbc();
        KnowledgeCrawlService crawler = new KnowledgeCrawlService(new JdbcTemplate(), mock(PersonalKnowledgeService.class)) {
            @Override
            String fetch(String url) {
                return "<html><head><title>Safe guide</title></head><body><script>ignore()</script><main>Verified evidence</main></body></html>";
            }
        };
        WebResearchService service = new WebResearchService(crawler, jdbc, new com.fasterxml.jackson.databind.ObjectMapper());

        var page = service.fetch(actor, "https://93.184.216.34/guide?token=secret");

        assertNotNull(page.taskId());
        assertEquals("https://93.184.216.34/guide", page.displayUrl());
        assertTrue(page.content().contains("Verified evidence"));
        assertFalse(page.content().contains("ignore()"));
        assertEquals("SUCCESS", jdbc.queryForObject("SELECT status FROM web_research_task WHERE id=?", String.class, page.taskId()));
        assertEquals("https://93.184.216.34/guide", jdbc.queryForObject("SELECT url FROM web_research_page WHERE task_id=?", String.class, page.taskId()));
        assertEquals(page.contentHash(), jdbc.queryForObject("SELECT content_hash FROM web_research_page WHERE task_id=?", String.class, page.taskId()));
        assertFalse(jdbc.queryForObject("SELECT query_text FROM web_research_task WHERE id=?", String.class, page.taskId()).contains("secret"));
    }

    @Test
    void fetchGithubRepositoryUsesOfficialMetadataAndReadmeApi() {
        var jdbc = researchJdbc();
        List<String> requests = new java.util.ArrayList<>();
        KnowledgeCrawlService crawler = new KnowledgeCrawlService(new JdbcTemplate(), mock(PersonalKnowledgeService.class)) {
            @Override
            String fetch(String url, String accept) {
                requests.add(url + " | " + accept);
                if (url.endsWith("/readme")) {
                    assertEquals("application/vnd.github.raw+json", accept);
                    return "# SmartOps Agent\n\nOfficial README evidence.";
                }
                assertEquals("https://api.github.com/repos/smartops/agent", url);
                return "{\"full_name\":\"smartops/agent\"}";
            }

            @Override
            String fetch(String url) {
                throw new AssertionError("Repository root must not use generic HTML fetch");
            }
        };
        WebResearchService service = new WebResearchService(crawler, jdbc, new com.fasterxml.jackson.databind.ObjectMapper());

        var page = service.fetch(actor, "https://github.com/smartops/agent?token=secret");

        assertEquals("smartops/agent · README", page.title());
        assertEquals("https://github.com/smartops/agent", page.displayUrl());
        assertTrue(page.content().contains("Official README evidence."));
        assertEquals(2, requests.size());
        assertEquals("https://api.github.com/repos/smartops/agent/readme | application/vnd.github.raw+json", requests.get(1));
        assertEquals("SUCCESS", jdbc.queryForObject("SELECT status FROM web_research_task WHERE id=?", String.class, page.taskId()));
        assertEquals(page.contentHash(), jdbc.queryForObject("SELECT content_hash FROM web_research_page WHERE task_id=?", String.class, page.taskId()));
        assertFalse(jdbc.queryForObject("SELECT query_text FROM web_research_task WHERE id=?", String.class, page.taskId()).contains("secret"));
    }

    @Test
    void githubNonRepositoryPathKeepsGenericSafeFetch() {
        var jdbc = researchJdbc();
        List<String> requests = new java.util.ArrayList<>();
        KnowledgeCrawlService crawler = new KnowledgeCrawlService(new JdbcTemplate(), mock(PersonalKnowledgeService.class)) {
            @Override
            String fetch(String url) {
                requests.add(url);
                return "<html><head><title>Organization repositories</title></head><body>Public list</body></html>";
            }

            @Override
            String fetch(String url, String accept) {
                throw new AssertionError("Non-repository path must not use repository API");
            }
        };
        WebResearchService service = new WebResearchService(crawler, jdbc, new com.fasterxml.jackson.databind.ObjectMapper());

        var page = service.fetch(actor, "https://github.com/orgs/smartops/repositories");

        assertEquals("Organization repositories", page.title());
        assertEquals(List.of("https://github.com/orgs/smartops/repositories"), requests);
        assertTrue(page.content().contains("Organization repositories"));
        assertTrue(page.content().contains("Public list"));
    }

    @Test
    void rejectsBlankQueryBeforeNetworkOrDatabase() {
        KnowledgeCrawlService crawler = new KnowledgeCrawlService(new JdbcTemplate(), mock(PersonalKnowledgeService.class));
        WebResearchService service = new WebResearchService(crawler, new JdbcTemplate(), new com.fasterxml.jackson.databind.ObjectMapper());

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.search(actor, " ", "ALL", 8));

        assertEquals("WEB_RESEARCH_QUERY_REQUIRED", failure.getMessage());
    }

    private static JdbcTemplate researchJdbc() {
        var dataSource = new org.springframework.jdbc.datasource.DriverManagerDataSource(
                "jdbc:h2:mem:web-research-fetch-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        var jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE web_research_task (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, task_type VARCHAR(32) NOT NULL, query_text CLOB NOT NULL, result_count INT NOT NULL DEFAULT 0, status VARCHAR(32) NOT NULL, error_code VARCHAR(500), created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMP NULL)");
        jdbc.execute("CREATE TABLE web_research_page (task_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, url VARCHAR(255) NOT NULL, title VARCHAR(255) NOT NULL, excerpt CLOB NOT NULL, content CLOB NOT NULL, content_hash VARCHAR(64) NOT NULL, fetched_at TIMESTAMP NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        return jdbc;
    }
}
