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

    /** 会话召回方向与 match 相反：incident_key 出现在用户这句话里才算命中，且只看本人 ACTIVE。 */
    @Test
    void recallFindsMemoriesWhoseIncidentKeyAppearsInTheQuestion() {
        var nginx = service.recordConfirmed(1L, "nginx:502", "TOOL", "先查 upstream 状态", "trace-1");
        service.recordConfirmed(1L, "redis:oom", "TOOL", "扩容内存", "trace-2");
        service.recordConfirmed(2L, "nginx:502", "TOOL", "别人的记忆", "trace-3");

        assertThat(service.recall(1L, "线上 nginx:502 又报了，帮我看看", 5))
                .extracting(OperatorMemoryService.Memory::id).containsExactly(nginx.id());
        assertThat(service.recall(3L, "线上 nginx:502 又报了", 5)).isEmpty();

        service.disable(1L, nginx.id());
        assertThat(service.recall(1L, "线上 nginx:502 又报了", 5)).isEmpty();
    }

    /** 聊天教给的规则单独标 CHAT_PREFERENCE，同一句话重复回写走唯一键幂等。 */
    @Test
    void chatPreferenceIsIdempotentAndLabelled() {
        var first = service.recordChatPreference(1L, "nginx:502", "先看网关日志", "chat-pref:abc");
        var second = service.recordChatPreference(1L, "nginx:502", "先看网关日志", "chat-pref:abc");

        assertThat(first.memoryType()).isEqualTo("CHAT_PREFERENCE");
        assertThat(second.id()).isEqualTo(first.id());
    }
}
