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
        jdbc.execute("CREATE TABLE agent_decision_loop (id VARCHAR(32) PRIMARY KEY, user_id BIGINT NOT NULL, incident_key VARCHAR(255) NOT NULL, title VARCHAR(255) NOT NULL, source_type VARCHAR(32) NOT NULL DEFAULT 'MANUAL', source_ref VARCHAR(128), stage VARCHAR(32) NOT NULL DEFAULT 'ANALYZE', severity VARCHAR(32) NOT NULL DEFAULT 'MEDIUM', symptom TEXT, analysis TEXT, evidence_json TEXT, memory_refs TEXT, recommendation TEXT, decision TEXT, decision_basis TEXT, requires_human BOOLEAN NOT NULL DEFAULT FALSE, outcome VARCHAR(32), lesson TEXT, learned_memory_ids TEXT, learned_count INT NOT NULL DEFAULT 0, confidence DOUBLE NOT NULL DEFAULT 0.5, reviewed_at TIMESTAMP NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbc.execute("CREATE TABLE inspector_event (id VARCHAR(32) PRIMARY KEY, task_id VARCHAR(128) NOT NULL, target VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL, severity VARCHAR(32) NOT NULL, category VARCHAR(64), agent_claim TEXT, reason TEXT NOT NULL, recommendation TEXT, requires_human BOOLEAN NOT NULL, metadata_json TEXT, created_at TIMESTAMP NOT NULL)");
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
        jdbc.update("INSERT INTO inspector_event(id,task_id,target,status,severity,category,agent_claim,reason,recommendation,requires_human,created_at) VALUES('INS-1','TASK-1','AGENT','PASS','HIGH','redis','redis 连接超时','内存使用率过高','扩容并重启 redis',FALSE,CURRENT_TIMESTAMP)");
        jdbc.update("INSERT INTO inspection_evidence(event_id,content,source,score) VALUES('INS-1','redis info 显示 maxmemory 打满','redis-cli',0.92)");
        jdbc.update("INSERT INTO inspection_verification(event_id,resolved,status,verified_at) VALUES('INS-1',TRUE,'PASS',CURRENT_TIMESTAMP)");

        List<Map<String, Object>> loops = service.list(1L, 10);
        assertThat(loops).hasSize(1);
        Map<String, Object> detail = service.detail(1L, String.valueOf(loops.get(0).get("id")));
        assertThat(detail.get("stage")).isEqualTo("LEARNED");
        assertThat(detail.get("sourceType")).isEqualTo("INSPECTOR");
        assertThat((List<?>) detail.get("learnedMemories")).hasSize(1);
    }
}
