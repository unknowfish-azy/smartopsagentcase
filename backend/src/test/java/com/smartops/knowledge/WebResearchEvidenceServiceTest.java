package com.smartops.knowledge;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class WebResearchEvidenceServiceTest {
    private final SessionUser actor = new SessionUser(1L, "alice", "user");

    @Test
    void compareReturnsVerifiableSignalsAndOverlapWithoutTruthClaim() {
        JdbcTemplate jdbc = evidenceDatabase();
        String content = "Kubernetes NetworkPolicy selects pods by labels.";
        insertWebPage(jdbc, 1L, 1L, "https://docs.example.com/guide", content, "FETCH");
        insertWebPage(jdbc, 2L, 1L, "https://github.com/smartops/guide", content, "RADAR");
        WebResearchEvidenceService service = new WebResearchEvidenceService(jdbc);

        var comparison = service.compare(actor, List.of(1L, 2L));

        assertEquals(2, comparison.items().size());
        assertEquals(1, comparison.pairs().size());
        assertTrue(comparison.pairs().get(0).differentHosts());
        assertEquals(1.0, comparison.pairs().get(0).textOverlap());
        assertEquals("HIGH", comparison.pairs().get(0).overlapLevel());
        assertEquals("UNKNOWN", comparison.items().get(0).signals().stream()
                .filter(signal -> signal.code().equals("SOURCE_AUTHORITY")).findFirst().orElseThrow().state());
        assertEquals("PASS", comparison.items().get(0).signals().stream()
                .filter(signal -> signal.code().equals("PROVENANCE")).findFirst().orElseThrow().state());
        assertTrue(comparison.disclaimer().contains("不构成真实性评分"));
    }

    @Test
    void compareRejectsAnotherUsersSnapshot() {
        JdbcTemplate jdbc = evidenceDatabase();
        insertWebPage(jdbc, 1L, 1L, "https://docs.example.com/guide", "first page", "FETCH");
        insertWebPage(jdbc, 2L, 2L, "https://other.example.com/guide", "second page", "FETCH");
        WebResearchEvidenceService service = new WebResearchEvidenceService(jdbc);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.compare(actor, List.of(1L, 2L)));

        assertEquals(404, failure.getCode());
        assertEquals("WEB_RESEARCH_PAGE_NOT_FOUND", failure.getMessage());
    }

    @Test
    void compareRequiresTwoDistinctTasks() {
        WebResearchEvidenceService service = new WebResearchEvidenceService(new JdbcTemplate());

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.compare(actor, List.of(1L, 1L)));

        assertEquals(400, failure.getCode());
        assertEquals("WEB_RESEARCH_COMPARE_SIZE", failure.getMessage());
    }

    @Test
    void crawlDiffShowsTitleHashAndLineChanges() {
        JdbcTemplate jdbc = evidenceDatabase();
        insertCrawlPage(jdbc, 10L, "Old title", "line one\nold line\nline three");
        insertCrawlPage(jdbc, 11L, "New title", "line one\nnew line\nline three");
        WebResearchEvidenceService service = new WebResearchEvidenceService(jdbc);

        var diff = service.diffCrawlPage(actor, 11L);

        assertTrue(diff.hasPrevious());
        assertEquals(10L, diff.previousPageId());
        assertTrue(diff.fields().stream().filter(field -> field.field().equals("title")).findFirst().orElseThrow().changed());
        assertTrue(diff.fields().stream().filter(field -> field.field().equals("contentHash")).findFirst().orElseThrow().changed());
        assertTrue(diff.lines().stream().anyMatch(line -> line.type().equals("REMOVED") && line.text().equals("old line")));
        assertTrue(diff.lines().stream().anyMatch(line -> line.type().equals("ADDED") && line.text().equals("new line")));
        assertTrue(diff.lines().stream().anyMatch(line -> line.type().equals("CONTEXT") && line.text().equals("line one")));
    }

    @Test
    void crawlDiffRejectsAnotherUsersSnapshot() {
        JdbcTemplate jdbc = evidenceDatabase();
        insertCrawlPage(jdbc, 10L, "Private", "content");
        jdbc.update("UPDATE knowledge_crawl_page SET user_id=2 WHERE id=10");
        WebResearchEvidenceService service = new WebResearchEvidenceService(jdbc);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.diffCrawlPage(actor, 10L));

        assertEquals(404, failure.getCode());
        assertEquals("KNOWLEDGE_CRAWL_PAGE_NOT_FOUND", failure.getMessage());
    }

    @Test
    void firstCrawlSnapshotHasNoComparisonBase() {
        JdbcTemplate jdbc = evidenceDatabase();
        insertCrawlPage(jdbc, 10L, "First", "content");
        WebResearchEvidenceService service = new WebResearchEvidenceService(jdbc);

        var diff = service.diffCrawlPage(actor, 10L);

        assertFalse(diff.hasPrevious());
        assertNull(diff.previousPageId());
        assertTrue(diff.fields().isEmpty());
    }

    private static JdbcTemplate evidenceDatabase() {
        var dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:web-evidence-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE web_research_task (id BIGINT PRIMARY KEY,user_id BIGINT NOT NULL,task_type VARCHAR(24) NOT NULL)");
        jdbc.execute("CREATE TABLE web_research_page (task_id BIGINT PRIMARY KEY,user_id BIGINT NOT NULL,url VARCHAR(255) NOT NULL,title VARCHAR(255) NOT NULL,content CLOB NOT NULL,content_hash VARCHAR(64) NOT NULL,fetched_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE knowledge_crawl_page (id BIGINT PRIMARY KEY,source_id BIGINT NOT NULL,user_id BIGINT NOT NULL,url VARCHAR(512) NOT NULL,title VARCHAR(255),content_md CLOB,content_hash VARCHAR(64),change_type VARCHAR(16),fetched_at TIMESTAMP NOT NULL)");
        return jdbc;
    }

    private static void insertWebPage(JdbcTemplate jdbc, long taskId, long userId, String url, String content, String taskType) {
        jdbc.update("INSERT INTO web_research_task(id,user_id,task_type) VALUES(?,?,?)", taskId, userId, taskType);
        jdbc.update("INSERT INTO web_research_page(task_id,user_id,url,title,content,content_hash,fetched_at) VALUES(?,?,?,?,?,?,?)",
                taskId, userId, url, "Page " + taskId, content, KnowledgeCrawlService.sha256(content), Timestamp.from(Instant.EPOCH));
    }

    private static void insertCrawlPage(JdbcTemplate jdbc, long id, String title, String content) {
        jdbc.update("INSERT INTO knowledge_crawl_page(id,source_id,user_id,url,title,content_md,content_hash,change_type,fetched_at) VALUES(?,?,?,?,?,?,?,?,?)",
                id, 3L, 1L, "https://docs.example.com/guide", title, content,
                KnowledgeCrawlService.sha256(content), id == 10L ? "ADDED" : "UPDATED", Timestamp.from(Instant.EPOCH.plusSeconds(id)));
    }
}
