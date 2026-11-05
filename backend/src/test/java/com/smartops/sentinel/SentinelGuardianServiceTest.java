package com.smartops.sentinel;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.service.IncidentRecommendationService;
import com.smartops.service.OperatorMemoryService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class SentinelGuardianServiceTest {

    private JdbcTemplate jdbc;
    private SentinelGuardianService guardian;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource(
                "jdbc:h2:mem:sentinel-guardian-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE operator_memory (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, incident_key VARCHAR(255) NOT NULL, memory_type VARCHAR(32) NOT NULL, preferred_action TEXT NOT NULL, source_refs TEXT, evidence_count INT NOT NULL, confidence DOUBLE NOT NULL, status VARCHAR(32) NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE sentinel_task (id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, name VARCHAR(128) NOT NULL, kind VARCHAR(24) NOT NULL, target VARCHAR(255) NOT NULL, interval_sec INT NOT NULL, template_id BIGINT, enabled TINYINT NOT NULL DEFAULT 1)");
        jdbc.execute("CREATE TABLE sentinel_threshold_template (id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, name VARCHAR(128) NOT NULL, rules_json TEXT NOT NULL, severity VARCHAR(4) NOT NULL, debounce_sec INT NOT NULL, updated_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE sentinel_metric_sample (id BIGINT AUTO_INCREMENT PRIMARY KEY, task_id BIGINT NOT NULL, sampled_at TIMESTAMP NOT NULL, metric VARCHAR(64) NOT NULL, value_num DOUBLE, abnormal TINYINT NOT NULL DEFAULT 0)");
        jdbc.execute("CREATE TABLE sentinel_alert (id BIGINT PRIMARY KEY, task_id BIGINT, severity VARCHAR(4) NOT NULL, status VARCHAR(16) NOT NULL, title VARCHAR(200) NOT NULL, metric VARCHAR(64), observed_value VARCHAR(128), threshold_value VARCHAR(128), detail_json TEXT, fired_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE sentinel_guardian_evidence (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, alert_id BIGINT NOT NULL, kind VARCHAR(32) NOT NULL, title VARCHAR(255) NOT NULL, detail VARCHAR(800), created_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE sentinel_learning_profile (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, task_id BIGINT NOT NULL, task_name VARCHAR(128), metric VARCHAR(64) NOT NULL, operator VARCHAR(8), sample_count INT NOT NULL, avg_value DOUBLE, p95_value DOUBLE, min_value DOUBLE, max_value DOUBLE, current_threshold DOUBLE, suggested_threshold DOUBLE, status VARCHAR(16) NOT NULL, learned_at TIMESTAMP NOT NULL, applied_at TIMESTAMP NULL, updated_at TIMESTAMP NOT NULL, CONSTRAINT uk_learning_task_metric UNIQUE (user_id, task_id, metric))");

        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,template_id,enabled) VALUES(1,1,'web-01','system','ssh://web-01',60,1,1)");
        jdbc.update("INSERT INTO sentinel_threshold_template(id,user_id,name,rules_json,severity,debounce_sec,updated_at) VALUES(1,1,'默认模板','[{\"metric\":\"cpu\",\"operator\":\"gt\",\"value\":90}]','P2',300,CURRENT_TIMESTAMP)");

        var memories = new OperatorMemoryService(jdbc);
        guardian = new SentinelGuardianService(jdbc, new ObjectMapper(), memories, new IncidentRecommendationService());
    }

    @Test
    @DisplayName("告警自动取证：补齐基线、同类告警与记忆证据，且可手工重跑")
    void collectsEvidenceForAlerts() {
        seedSamples(1, "cpu", 60d, 30, 1d);
        fireAlert(1, "cpu");

        int enriched = guardian.enrichPending(10);
        assertThat(enriched).isEqualTo(1);

        List<Map<String, Object>> evidence = guardian.listEvidence(1L, 20);
        assertThat(evidence).hasSize(2);
        assertThat(evidence).extracting(item -> item.get("kind"))
                .containsExactlyInAnyOrder("BASELINE", "RELATED_ALERT");
        assertThat(String.valueOf(evidence.get(0).get("detail"))).isNotBlank();

        Map<String, Object> recollected = guardian.collect(1L, 1L);
        assertThat((List<?>) recollected.get("evidence")).hasSize(2);

        assertThat(guardian.stats(1L).get("evidence")).isEqualTo(2L);
    }

    @Test
    @DisplayName("持续学习：学出基线给出建议，人工确认后写回阈值模板")
    void learnsBaselineAndAppliesSuggestion() {
        seedSamples(1, "cpu", 100d, 30, 1d);

        assertThat(guardian.learnAll()).isEqualTo(1);
        List<Map<String, Object>> profiles = guardian.listProfiles(1L);
        assertThat(profiles).hasSize(1);
        Map<String, Object> profile = profiles.get(0);
        assertThat(profile.get("status")).isEqualTo("SUGGESTED");
        assertThat(profile.get("sampleCount")).isEqualTo(30);
        assertThat(((Number) profile.get("suggestedThreshold")).doubleValue()).isEqualTo(116.15d);

        guardian.apply(1L, ((Number) profile.get("id")).longValue());

        List<String> rules = jdbc.queryForList("SELECT rules_json FROM sentinel_threshold_template WHERE id=1", String.class);
        assertThat(rules.get(0)).contains("116.15");
        assertThat(guardian.listProfiles(1L).get(0).get("status")).isEqualTo("APPLIED");
        assertThat(guardian.stats(1L).get("applied")).isEqualTo(1L);
    }

    private void seedSamples(long taskId, String metric, double value, int count, double noise) {
        Instant base = Instant.now().minusSeconds(count * 60L);
        for (int index = 0; index < count; index++) {
            jdbc.update("INSERT INTO sentinel_metric_sample(task_id,sampled_at,metric,value_num,abnormal) VALUES(?,?,?,?,0)",
                    taskId, Timestamp.from(base.plusSeconds(index * 60L)), metric, value + (index % 2 == 0 ? noise : -noise));
        }
    }

    private void fireAlert(long id, String metric) {
        jdbc.update("INSERT INTO sentinel_alert(id,task_id,severity,status,title,metric,observed_value,threshold_value,fired_at) "
                        + "VALUES(?,1,'P2','OPEN','web-01：cpu > 90',?,'120','cpu > 90',CURRENT_TIMESTAMP)",
                id, metric);
    }
}
