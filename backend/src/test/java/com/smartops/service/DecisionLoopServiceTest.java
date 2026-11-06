package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class DecisionLoopServiceTest {

    private JdbcTemplate jdbc;
    private OperatorMemoryService memories;
    private DecisionLoopService service;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource(
                "jdbc:h2:mem:decision-loop-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE operator_memory (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, incident_key VARCHAR(255) NOT NULL, memory_type VARCHAR(32) NOT NULL, preferred_action TEXT NOT NULL, source_refs TEXT, evidence_count INT NOT NULL, confidence DOUBLE NOT NULL, status VARCHAR(32) NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE agent_decision_loop (id VARCHAR(32) PRIMARY KEY, user_id BIGINT NOT NULL, incident_key VARCHAR(255) NOT NULL, title VARCHAR(255) NOT NULL, source_type VARCHAR(32) NOT NULL DEFAULT 'MANUAL', source_ref VARCHAR(128), stage VARCHAR(32) NOT NULL DEFAULT 'ANALYZE', severity VARCHAR(32) NOT NULL DEFAULT 'MEDIUM', symptom TEXT, analysis TEXT, evidence_json TEXT, memory_refs TEXT, recommendation TEXT, decision TEXT, decision_basis TEXT, requires_human BOOLEAN NOT NULL DEFAULT FALSE, outcome VARCHAR(32), lesson TEXT, learned_memory_ids TEXT, learned_count INT NOT NULL DEFAULT 0, confidence DOUBLE NOT NULL DEFAULT 0.5, reviewed_at TIMESTAMP NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, CONSTRAINT uq_agent_decision_loop_user_source UNIQUE (user_id, source_type, source_ref))");
        jdbc.execute("CREATE TABLE inspector_event (id VARCHAR(32) PRIMARY KEY, task_id VARCHAR(128) NOT NULL, target VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL, severity VARCHAR(32) NOT NULL, category VARCHAR(64), agent_claim TEXT, reason TEXT NOT NULL, recommendation TEXT, requires_human BOOLEAN NOT NULL, metadata_json TEXT, user_id BIGINT NULL, created_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE inspection_evidence (id BIGINT AUTO_INCREMENT PRIMARY KEY, event_id VARCHAR(32) NOT NULL, content TEXT NOT NULL, source VARCHAR(500), version VARCHAR(100), score DOUBLE)");
        jdbc.execute("CREATE TABLE inspection_verification (id BIGINT AUTO_INCREMENT PRIMARY KEY, event_id VARCHAR(32) NOT NULL, resolved BOOLEAN, status VARCHAR(100), details_json TEXT, verified_at TIMESTAMP NOT NULL)");
        memories = new OperatorMemoryService(jdbc);
        service = new DecisionLoopService(jdbc, new ObjectMapper(), memories, new IncidentRecommendationService());
    }

    @Test
    @DisplayName("手工闭环：召回记忆 → 决策 → 复盘解决后置信度真实上调")
    void manualLoopLearnsFromResolvedReview() {
        Map<String, Object> created = service.create(1L,
                new DecisionLoopService.CreateRequest("nginx:502", "Nginx 502 排查", "HIGH",
                        "上游 502", "疑似 upstream 超时", List.of("error.log: upstream timed out")));
        String id = String.valueOf(created.get("id"));
        assertThat(created.get("stage")).isEqualTo("ANALYZE");

        var memory = memories.recordConfirmed(1L, "nginx:502", "TOOL", "重启 upstream 服务", "trace-1");

        Map<String, Object> recalled = service.recall(1L, id);
        assertThat(recalled.get("stage")).isEqualTo("MEMORIZE");
        assertThat((List<?>) recalled.get("memories")).hasSize(1);
        assertThat(String.valueOf(recalled.get("recommendation"))).contains("重启 upstream 服务");

        Map<String, Object> decided = service.decide(1L, id,
                new DecisionLoopService.DecideRequest(null, "先重启 upstream，再观察 5 分钟", "历史同类处置有效", false));
        assertThat(decided.get("stage")).isEqualTo("DECIDE");

        Map<String, Object> reviewed = service.review(1L, id,
                new DecisionLoopService.ReviewRequest("RESOLVED", "upstream 超时，重启后恢复"));
        assertThat(reviewed.get("stage")).isEqualTo("LEARNED");
        assertThat((List<?>) reviewed.get("learnedMemories")).hasSize(1);

        var updated = memories.match(1L, "nginx:502").get(0);
        assertThat(updated.id()).isEqualTo(memory.id());
        assertThat(updated.evidenceCount()).isEqualTo(2);
        assertThat(updated.confidence()).isCloseTo(0.6d, org.assertj.core.data.Offset.offset(1e-9));

        Map<String, Object> stats = service.stats(1L);
        assertThat(stats.get("total")).isEqualTo(1L);
        assertThat(stats.get("resolved")).isEqualTo(1L);
        assertThat(stats.get("learnedCount")).isEqualTo(1L);
        assertThat(stats.get("resolveRate")).isEqualTo(1.0d);
    }

    @Test
    @DisplayName("自动通道：Inspector 已验证事件会派生闭环并沉淀记忆")
    void inspectorEventIsDerivedAutomatically() {
        jdbc.update("INSERT INTO inspector_event(id,task_id,target,status,severity,category,agent_claim,reason,recommendation,requires_human,user_id,created_at) VALUES('INS-1','TASK-1','AGENT','PASS','HIGH','redis','redis 连接超时','内存使用率过高','扩容并重启 redis',FALSE,1,CURRENT_TIMESTAMP)");
        jdbc.update("INSERT INTO inspection_evidence(event_id,content,source,score) VALUES('INS-1','redis info 显示 maxmemory 打满','redis-cli',0.92)");
        jdbc.update("INSERT INTO inspection_verification(event_id,resolved,status,verified_at) VALUES('INS-1',TRUE,'PASS',CURRENT_TIMESTAMP)");

        List<Map<String, Object>> loops = service.list(1L, 10);
        assertThat(loops).hasSize(1);
        Map<String, Object> detail = service.detail(1L, String.valueOf(loops.get(0).get("id")));
        assertThat(detail.get("stage")).isEqualTo("LEARNED");
        assertThat(detail.get("sourceType")).isEqualTo("INSPECTOR");
        assertThat((List<?>) detail.get("learnedMemories")).hasSize(1);
    }

    /** SEC-08：无归属或属于他人的 Inspector 事件不得投影进当前用户闭环。 */
    @Test
    @DisplayName("权限 scope：全局/他人 Inspector 事件不投影")
    void unownedOrOtherUsersInspectorEventsAreNotProjected() {
        jdbc.update("INSERT INTO inspector_event(id,task_id,target,status,severity,category,agent_claim,reason,recommendation,requires_human,user_id,created_at) VALUES('INS-GLOBAL','TASK-G','AGENT','PASS','HIGH','redis','x','全局巡检','y',FALSE,NULL,CURRENT_TIMESTAMP)");
        jdbc.update("INSERT INTO inspector_event(id,task_id,target,status,severity,category,agent_claim,reason,recommendation,requires_human,user_id,created_at) VALUES('INS-OTHER','TASK-O','AGENT','PASS','HIGH','redis','x','他人巡检','y',FALSE,2,CURRENT_TIMESTAMP)");

        assertThat(service.list(1L, 10)).isEmpty();
        assertThat(service.list(2L, 10)).hasSize(1);
        assertThat(service.list(2L, 10).get(0).get("sourceRef")).isEqualTo("INS-OTHER");
    }

    /** SEC-10 / TM-28：同一闭环同结论重复 review 幂等，不重复回写记忆、不累加 learned_count。 */
    @Test
    @DisplayName("幂等：连续 5 次相同结论 review 只学习一次")
    void repeatedReviewLearnsOnlyOnce() {
        Map<String, Object> created = service.create(1L,
                new DecisionLoopService.CreateRequest("nginx:502", "Nginx 502 排查", "HIGH", "上游 502", "疑似超时", List.of()));
        String id = String.valueOf(created.get("id"));
        var memory = memories.recordConfirmed(1L, "nginx:502", "TOOL", "重启 upstream 服务", "trace-1");
        service.recall(1L, id);

        for (int attempt = 0; attempt < 5; attempt++) {
            Map<String, Object> reviewed = service.review(1L, id,
                    new DecisionLoopService.ReviewRequest(attempt % 2 == 0 ? "RESOLVED" : "resolved", "第 " + attempt + " 次复盘"));
            assertThat(reviewed.get("stage")).isEqualTo("LEARNED");
            assertThat(reviewed.get("learnedCount")).isEqualTo(1);
            assertThat((List<?>) reviewed.get("learnedMemories")).hasSize(1);
        }

        var updated = memories.match(1L, "nginx:502").get(0);
        assertThat(updated.id()).isEqualTo(memory.id());
        assertThat(updated.evidenceCount()).isEqualTo(2);
        assertThat(updated.confidence()).isCloseTo(0.6d, org.assertj.core.data.Offset.offset(1e-9));
        assertThat(memories.list(1L)).hasSize(1);
    }

    /** SEC-10：结论翻转视为新信息，允许再次学习（不误判为重复）。 */
    @Test
    @DisplayName("结论翻转会再次学习")
    void flippedOutcomeLearnsAgain() {
        Map<String, Object> created = service.create(1L,
                new DecisionLoopService.CreateRequest("nginx:502", "Nginx 502 排查", "HIGH", "上游 502", "疑似超时", List.of()));
        String id = String.valueOf(created.get("id"));
        var memory = memories.recordConfirmed(1L, "nginx:502", "TOOL", "重启 upstream 服务", "trace-1");
        service.recall(1L, id);

        service.review(1L, id, new DecisionLoopService.ReviewRequest("RESOLVED", "已恢复"));
        assertThat(memories.match(1L, "nginx:502").get(0).confidence())
                .isCloseTo(0.6d, org.assertj.core.data.Offset.offset(1e-9));

        Map<String, Object> flipped = service.review(1L, id, new DecisionLoopService.ReviewRequest("UNRESOLVED", "问题复现"));
        assertThat(flipped.get("outcome")).isEqualTo("UNRESOLVED");
        assertThat(flipped.get("learnedCount")).isEqualTo(1);

        var updated = memories.match(1L, "nginx:502").get(0);
        assertThat(updated.id()).isEqualTo(memory.id());
        assertThat(updated.evidenceCount()).isEqualTo(2);
        assertThat(updated.confidence()).isCloseTo(0.45d, org.assertj.core.data.Offset.offset(1e-9));
    }

    /** SEC-10 / TM-29：并发 GET 同时同步同一 Inspector 事件，唯一键兜底且不抛 500。 */
    @Test
    @DisplayName("并发同步同一事件只产生一条闭环")
    void concurrentSyncCreatesSingleLoop() throws Exception {
        jdbc.update("INSERT INTO inspector_event(id,task_id,target,status,severity,category,agent_claim,reason,recommendation,requires_human,user_id,created_at) VALUES('INS-C','TASK-C','AGENT','VIOLATION','HIGH','redis','x','并发巡检','y',FALSE,1,CURRENT_TIMESTAMP)");

        int threads = 8;
        var pool = java.util.concurrent.Executors.newFixedThreadPool(threads);
        var start = new java.util.concurrent.CountDownLatch(1);
        var done = new java.util.concurrent.CountDownLatch(threads);
        var failures = java.util.Collections.synchronizedList(new java.util.ArrayList<Throwable>());
        try {
            for (int i = 0; i < threads; i++) {
                pool.submit(() -> {
                    try {
                        start.await();
                        service.list(1L, 10);
                    } catch (Throwable error) {
                        failures.add(error);
                    } finally {
                        done.countDown();
                    }
                });
            }
            start.countDown();
            assertThat(done.await(10, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
        } finally {
            pool.shutdownNow();
        }

        assertThat(failures).isEmpty();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM agent_decision_loop WHERE user_id=1", Integer.class)).isEqualTo(1);
    }
}
