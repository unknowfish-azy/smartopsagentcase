package com.smartops.knowledge;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

/** T35b 调度竞争 claim（D5：DB 条件更新，不引 Redis 锁）：多副本仅一成功、租约过期可重领。 */
class KnowledgeCrawlClaimTest {

    private KnowledgeCrawlService service(JdbcTemplate jdbc, WebResearchMetrics metrics) {
        return new KnowledgeCrawlService(jdbc, mock(com.smartops.service.PersonalKnowledgeService.class),
                new com.smartops.service.KnowledgeCandidateService(jdbc, null,
                        mock(com.smartops.service.PersonalKnowledgeService.class)), metrics, null);
    }

    private JdbcTemplate sourceJdbc() {
        var jdbc = new JdbcTemplate(new org.springframework.jdbc.datasource.DriverManagerDataSource(
                "jdbc:h2:mem:wr-claim-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        jdbc.execute("CREATE TABLE knowledge_crawl_source (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, library_id BIGINT NULL, name VARCHAR(255) NULL, seed_url VARCHAR(255) NULL, max_pages INT NULL, depth INT NULL, last_run_at TIMESTAMP NULL, last_status VARCHAR(24) NULL, last_error VARCHAR(500) NULL, monitor_enabled BOOLEAN NOT NULL DEFAULT FALSE, monitor_interval_minutes INT NOT NULL DEFAULT 60, next_run_at TIMESTAMP NULL, claim_token VARCHAR(64) NULL, claim_expiry TIMESTAMP NULL, created_at TIMESTAMP NULL)");
        return jdbc;
    }

    private void insertDueSource(JdbcTemplate jdbc, long userId) {
        jdbc.update("INSERT INTO knowledge_crawl_source(user_id,library_id,name,seed_url,max_pages,depth,monitor_enabled,next_run_at) VALUES(?,?,?,?,?,?,TRUE,?)",
                userId, 1L, "源", "https://example.com", 1, 0, Timestamp.from(Instant.now().minusSeconds(60)));
    }

    @Test
    void concurrentClaimsOnlyOneWins() throws Exception {
        var jdbc = sourceJdbc();
        insertDueSource(jdbc, 7L);
        var service = service(jdbc, null);

        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch ready = new CountDownLatch(4);
        final KnowledgeCrawlService claimService = service;
        List<Future<Object>> results = new java.util.ArrayList<>();
        for (int i = 0; i < 4; i++) {
            results.add(pool.submit(() -> {
                ready.countDown();
                ready.await(2, TimeUnit.SECONDS);
                try {
                    return claimService.claimNextSource();
                } catch (Exception failure) {
                    return failure;
                }
            }));
        }
        pool.shutdown();
        long winners = 0, losers = 0;
        for (Future<Object> future : results) {
            Object value = future.get(5, TimeUnit.SECONDS);
            if (value instanceof KnowledgeCrawlService.ClaimedSource) winners++;
            else losers++;
        }
        assertTrue(winners >= 1);
        final long winnerCount = winners;
        assertEquals(1, winners, () -> "多副本竞争必须只有一个领取成功，实际 winners=" + winnerCount);
        assertEquals(3, losers);
        // 领取成功后 claim_token 非空、租约在将来
        var row = jdbc.queryForMap("SELECT claim_token, claim_expiry FROM knowledge_crawl_source WHERE id=1");
        assertNotNull(row.get("claim_token"));
        assertTrue(((Timestamp) row.get("claim_expiry")).after(Timestamp.from(Instant.now())));
    }

    @Test
    void expiredLeaseAllowsReclaim() {
        var jdbc = sourceJdbc();
        insertDueSource(jdbc, 7L);
        var service = service(jdbc, null);

        var first = service.claimNextSource();
        assertNotNull(first);

        // 租约未过期：其他副本不可领取
        assertNull(service.claimNextSource());

        // 租约过期（模拟副本中断）：可重新领取，UNCERTAIN 语义
        jdbc.update("UPDATE knowledge_crawl_source SET claim_expiry=? WHERE id=1",
                Timestamp.from(Instant.now().minusSeconds(30)));
        var reclaimed = service.claimNextSource();
        assertNotNull(reclaimed);
        assertNotEquals(first.token(), reclaimed.token());
    }

    @Test
    void noDueSourceReturnsNull() {
        var jdbc = sourceJdbc();
        var service = service(jdbc, null);
        assertNull(service.claimNextSource());
    }

    @Test
    void metricsTrackRealClaimEvents() {
        var jdbc = sourceJdbc();
        insertDueSource(jdbc, 7L);
        var registry = new io.micrometer.core.instrument.simple.SimpleMeterRegistry();
        var metrics = new WebResearchMetrics(registry);
        var service = service(jdbc, metrics);

        assertNotNull(service.claimNextSource());
        assertNull(service.claimNextSource());

        metrics.radarDue();
        metrics.radarProcessed();
        metrics.radarSkipped();

        assertEquals(1, registry.counter("smartops.webresearch.radar.due").count());
        assertEquals(1, registry.counter("smartops.webresearch.radar.processed").count());
        assertEquals(1, registry.counter("smartops.webresearch.radar.skipped").count());
    }
}
