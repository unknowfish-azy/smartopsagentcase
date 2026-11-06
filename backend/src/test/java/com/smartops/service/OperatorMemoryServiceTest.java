package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.util.ArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class OperatorMemoryServiceTest {
    private JdbcTemplate jdbc;
    private OperatorMemoryService service;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:operator-memory-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE operator_memory (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, incident_key VARCHAR(255) NOT NULL, memory_type VARCHAR(32) NOT NULL, preferred_action TEXT NOT NULL, source_refs TEXT, evidence_count INT NOT NULL, confidence DOUBLE NOT NULL, status VARCHAR(32) NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)");
        service = new OperatorMemoryService(jdbc);
    }

    /** SEC-09：同用户并发创建必须各自返回自己那一条，而不是 MAX(id) 取到的最新行。 */
    @Test
    void concurrentCreatesReturnOwnRows() throws Exception {
        int threads = 8;
        var pool = Executors.newFixedThreadPool(threads);
        var start = new CountDownLatch(1);
        var futures = new ArrayList<java.util.concurrent.Future<OperatorMemoryService.Memory>>();
        try {
            for (int i = 0; i < threads; i++) {
                final int index = i;
                futures.add(pool.submit(() -> {
                    start.await();
                    return service.recordConfirmed(1L, "k-" + index, "TOOL", "action-" + index, "trace-" + index);
                }));
            }
            start.countDown();
            for (int i = 0; i < threads; i++) {
                var memory = futures.get(i).get(10, TimeUnit.SECONDS);
                assertThat(memory.incidentKey()).isEqualTo("k-" + i);
                assertThat(memory.preferredAction()).isEqualTo("action-" + i);
            }
            assertThat(futures.stream().map(future -> {
                try { return future.get().id(); } catch (Exception e) { throw new IllegalStateException(e); }
            })).doesNotHaveDuplicates();
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void recordsConfirmedMemoryAndMatchesOnlyActiveMemoryForCurrentUser() {
        var memory = service.recordConfirmed(1L, "nginx:502", "TOOL", "先查 upstream 状态", "trace-1");
        service.recordConfirmed(2L, "nginx:502", "TOOL", "private", "trace-2");
        assertThat(service.match(1L, "502")).extracting(OperatorMemoryService.Memory::id).containsExactly(memory.id());
        service.disable(1L, memory.id());
        assertThat(service.match(1L, "502")).isEmpty();
    }
}
