package com.smartops.knowledge;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

/** T35a 保留策略：N 版内不删 / 超限删旧 / 清理默认关 / 指标绑真实删除。 */
class WebResearchRetentionServiceTest {

    private JdbcTemplate jdbc;
    private SimpleMeterRegistry registry;

    private WebResearchRetentionService service(boolean enabled, int maxVersions) {
        var dataSource = new org.springframework.jdbc.datasource.DriverManagerDataSource(
                "jdbc:h2:mem:wr-retention-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE web_research_page (task_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, url VARCHAR(255) NOT NULL, title VARCHAR(255) NULL, excerpt CLOB NULL, content CLOB NULL, content_hash VARCHAR(64) NULL, fetched_at TIMESTAMP NULL, created_at TIMESTAMP NULL)");
        jdbc.execute("CREATE TABLE knowledge_crawl_page (id BIGINT AUTO_INCREMENT PRIMARY KEY, source_id BIGINT NOT NULL, user_id BIGINT NOT NULL, url VARCHAR(255) NOT NULL, title VARCHAR(255) NULL, content_md CLOB NULL, content_hash VARCHAR(64) NULL, change_type VARCHAR(24) NULL, fetched_at TIMESTAMP NULL)");
        jdbc.execute("CREATE TABLE knowledge_candidate (id BIGINT AUTO_INCREMENT PRIMARY KEY, source_task_id BIGINT NULL)");
        jdbc.update("INSERT INTO knowledge_candidate (source_task_id) VALUES (1)");
        registry = new SimpleMeterRegistry();
        return new WebResearchRetentionService(jdbc, new WebResearchMetrics(registry), enabled, maxVersions);
    }

    private void insertPage(String table, String urlColumn, String url, long groupKey) {
        if (table.equals("web_research_page")) {
            jdbc.update("INSERT INTO web_research_page(task_id,user_id,url) VALUES(?,?,?)",
                    System.nanoTime(), groupKey, url);
        } else {
            jdbc.update("INSERT INTO knowledge_crawl_page(source_id,user_id,url) VALUES(?,?,?)", groupKey, 7L, url);
        }
    }

    @Test
    void versionsWithinLimitAreKept() {
        var service = service(true, 20);
        for (int i = 0; i < 20; i++) insertPage("web_research_page", "url", "https://example.com/a", 7L);
        assertEquals(0, service.pruneAll());
        assertEquals(20, count("web_research_page"));
    }

    @Test
    void beyondLimitOldestAreDeletedAndCandidatesUntouched() {
        var service = service(true, 3);
        for (int i = 0; i < 5; i++) insertPage("web_research_page", "url", "https://example.com/a", 7L);
        for (int i = 0; i < 5; i++) insertPage("knowledge_crawl_page", "url", "https://example.com/b", 11L);
        // 另一个 URL 的 2 版不受其他 URL 超限影响
        insertPage("web_research_page", "url", "https://example.com/other", 7L);

        long deleted = service.pruneAll();

        assertEquals(4, deleted);
        assertEquals(3, countWhere("web_research_page", "url='https://example.com/a'"));
        assertEquals(3, countWhere("knowledge_crawl_page", "url='https://example.com/b'"));
        assertEquals(1, countWhere("web_research_page", "url='https://example.com/other'"));
        // 候选与正式知识不在清理范围
        assertEquals(1, count("knowledge_candidate"));
        assertTrue(registry.counter("smartops.webresearch.retention.deleted").count() >= 4);
    }

    @Test
    void disabledByDefaultDeletesNothing() {
        var service = service(false, 3);
        for (int i = 0; i < 8; i++) insertPage("web_research_page", "url", "https://example.com/a", 7L);
        assertEquals(0, service.pruneAll());
        assertEquals(8, count("web_research_page"));
        assertFalse(service.isEnabled());
    }

    private int count(String table) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Integer.class);
    }

    private int countWhere(String table, String where) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM " + table + " WHERE " + where, Integer.class);
    }
}
