package com.smartops.observability;

import com.smartops.common.ApiResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * T38：只读聚合与白名单的集成测试。
 * 直接用 Flyway 在测试库建好的真实表与真实列名插入夹具，验证聚合语义；不碰生产数据。
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:engineobs;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000",
        "smartops.sentinel.recovery.initial-delay-ms=86400000",
        "smartops.sentinel.dead-letter.initial-delay-ms=86400000"
})
class EngineObservabilityControllerTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired EngineObservabilityController controller;

    private static final long NOW = Instant.now().getEpochSecond();

    @BeforeEach
    void seed() {
        // 只清理本测试写入的表（真实表，满足非空/外键约束）
        jdbc.execute("DELETE FROM sentinel_alert_event");
        jdbc.execute("DELETE FROM sentinel_alert");
        jdbc.execute("DELETE FROM sentinel_task");
        jdbc.execute("DELETE FROM web_research_task");

        jdbc.update("INSERT INTO sentinel_task (user_id,name,kind,target,last_seen_at,last_status) "
                        + "VALUES (?,?,?,?,?,?)",
                1L, "采集-CPU", "COMMAND", "localhost",
                Timestamp.from(Instant.ofEpochSecond(NOW - 5)), "SUCCESS");
        jdbc.update("INSERT INTO web_research_task (user_id,task_type,status,error_code,finished_at) "
                        + "VALUES (?,?,?,?,?)",
                1L, "RADAR", "FAILED", "TIMEOUT",
                Timestamp.from(Instant.ofEpochSecond(NOW - 200)));
    }

    @Test
    @DisplayName("snapshot 返回全部引擎；training 恒 NOT_RUN")
    void snapshotAllEngines() {
        ApiResponse<EngineObservabilityController.Snapshot> resp = controller.snapshot();
        assertThat(resp.getCode()).isEqualTo(200);
        List<EngineStateClassifier.EngineState> states = resp.getData().engines();
        assertThat(states).extracting(EngineStateClassifier.EngineState::id)
                .contains("sentinel-poll", "web-research", "inspector", "decision-loop",
                        "operation-run", "training");
        var training = byId(states, "training");
        assertThat(training.status()).isEqualTo(EngineCatalog.Status.NOT_RUN);
    }

    @Test
    @DisplayName("真实事件正确分类：新鲜哨兵 RUNNING，超时失败研究 ERROR，空表 NO_DATA")
    void realFactClassification() {
        var states = controller.snapshot().getData().engines();
        var poll = byId(states, "sentinel-poll");
        assertThat(poll.status()).isEqualTo(EngineCatalog.Status.RUNNING);
        assertThat(poll.eventCount()).isEqualTo(1);

        var research = byId(states, "web-research");
        assertThat(research.status()).isEqualTo(EngineCatalog.Status.ERROR);
        assertThat(research.detail()).contains("最近事件异常");

        var inspector = byId(states, "inspector");
        assertThat(inspector.status()).isEqualTo(EngineCatalog.Status.NO_DATA);
    }

    @Test
    @DisplayName("event-stream 时间倒序；非法 engine 400；training 空")
    void eventStream() {
        // 建父 alert 满足外键
        jdbc.update("INSERT INTO sentinel_alert (severity,status,title,fired_at) VALUES (?,?,?,?)",
                "P2", "OPEN", "test", Timestamp.from(Instant.ofEpochSecond(NOW - 20)));
        Long alertId = jdbc.queryForObject("SELECT MAX(id) FROM sentinel_alert", Long.class);
        jdbc.update("INSERT INTO sentinel_alert_event (alert_id,at,kind) VALUES (?,?,?)",
                alertId, Timestamp.from(Instant.ofEpochSecond(NOW - 10)), "FIRED");
        jdbc.update("INSERT INTO sentinel_alert_event (alert_id,at,kind) VALUES (?,?,?)",
                alertId, Timestamp.from(Instant.ofEpochSecond(NOW - 3)), "RECOVERED");

        ApiResponse<?> ok = controller.eventStream("sentinel-guardian", 50);
        assertThat(ok.getCode()).isEqualTo(200);
        @SuppressWarnings("unchecked")
        List<EngineObservabilityController.EventItem> events =
                (List<EngineObservabilityController.EventItem>) ((Map<?, ?>) ok.getData()).get("events");
        assertThat(events).hasSize(2);
        assertThat(events.get(0).at()).isGreaterThan(events.get(1).at()); // 时间倒序

        assertThat(controller.eventStream("evil;drop", 10).getCode()).isEqualTo(400);
        var training = controller.eventStream("training", 10);
        assertThat(((Map<?, ?>) training.getData()).get("events")).isEqualTo(List.of());
    }

    private EngineStateClassifier.EngineState byId(
            List<EngineStateClassifier.EngineState> states, String id) {
        return states.stream().filter(s -> s.id().equals(id)).findFirst().orElseThrow();
    }
}
