package com.smartops.sentinel;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 预测面服务单测：真实哨兵采样 → ai-service 预测 → 前端契约。
 *
 * <p>重点不是"预测得准"，而是<b>口径不撒谎</b>：
 * 采样不足 / 上游不可达必须如实 unavailable，不能补合成曲线；
 * mode=model_status 决定 kind，统计降级不得被写成神经模型；
 * 取数必须按 user_id 隔离。
 */
class SentinelForecastServiceTest {

    private static final SessionUser ACTOR = new SessionUser(1L, "ops", "user");

    private JdbcTemplate jdbc;
    private FakeClient client;
    private SentinelForecastService service;

    /** 可控上游：记录收到的 payload，并按脚本返回。 */
    private static class FakeClient extends SentinelForecastClient {
        private Optional<Map<String, Object>> next = Optional.empty();
        private Map<String, Object> lastPayload;

        FakeClient() {
            super(new ObjectMapper(), "http://127.0.0.1:1", 1);
        }

        void returns(Map<String, Object> body) {
            this.next = Optional.ofNullable(body);
        }

        @Override
        public Optional<Map<String, Object>> forecast(Map<String, Object> payload) {
            this.lastPayload = payload;
            return next;
        }

        @Override
        public Optional<Map<String, Object>> modelInfo() {
            return Optional.of(Map.of("kind", "fallback", "torch_available", true));
        }
    }

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource(
                "jdbc:h2:mem:sentinel-forecast-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE sentinel_task (id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, "
                + "name VARCHAR(128) NOT NULL, kind VARCHAR(24) NOT NULL, target VARCHAR(255) NOT NULL, "
                + "interval_sec INT NOT NULL, template_id BIGINT, enabled TINYINT NOT NULL DEFAULT 1)");
        jdbc.execute("CREATE TABLE sentinel_metric_sample (id BIGINT AUTO_INCREMENT PRIMARY KEY, "
                + "task_id BIGINT NOT NULL, sampled_at TIMESTAMP NOT NULL, metric VARCHAR(64) NOT NULL, "
                + "value_num DOUBLE, abnormal TINYINT NOT NULL DEFAULT 0)");
        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,template_id,enabled) "
                + "VALUES(1,1,'web-01','system','ssh://web-01',60,NULL,1)");
        client = new FakeClient();
        service = new SentinelForecastService(jdbc, new ObjectMapper(), client, 5);
    }

    private void seed(long taskId, String metric, int count, int intervalSec, double startValue) {
        Instant base = Instant.parse("2026-11-16T10:00:00Z");
        for (int i = 0; i < count; i++) {
            jdbc.update("INSERT INTO sentinel_metric_sample(task_id,sampled_at,metric,value_num,abnormal) "
                            + "VALUES(?,?,?,?,0)",
                    taskId, Timestamp.from(base.plusSeconds((long) i * intervalSec)), metric, startValue + i * 2);
        }
    }

    private Map<String, Object> upstream(String mode, String status, List<Map<String, Object>> points) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("mode", mode);
        body.put("model_status", status);
        body.put("model_status_detail", "权重缺失");
        body.put("points", points);
        body.put("risk_score", 12.5);
        body.put("risk_level", "low");
        return body;
    }

    private Map<String, Object> point(int step, double value, double lower, double upper) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("step", step);
        row.put("value", value);
        row.put("lower", lower);
        row.put("upper", upper);
        return row;
    }

    @Test
    @DisplayName("catalog 只列出确有采样的槽位，并给出真实指标与采样间隔")
    void catalogOnlyListsSampledSlots() {
        seed(1, "cpu", 30, 30, 40d);

        Map<String, Object> catalog = service.catalog(1L);
        List<Map<String, Object>> slots = (List<Map<String, Object>>) catalog.get("slots");
        assertThat(slots).hasSize(1);
        assertThat(slots.get(0).get("key")).isEqualTo("ect");
        assertThat(slots.get(0).get("metric")).isEqualTo("cpu");
        assertThat(slots.get(0).get("sampleCount")).isEqualTo(30);
        assertThat(slots.get(0).get("sampleIntervalSec")).isEqualTo(30);
    }

    @Test
    @DisplayName("正常链路：透传真实序列与预测点，steps 按采样间隔换算")
    void forecastReturnsRealSeriesAndConvertedPoints() {
        seed(1, "cpu", 40, 30, 40d);
        List<Map<String, Object>> points = new ArrayList<>();
        points.add(point(1, 120, 110, 130));
        points.add(point(2, 125, 115, 135));
        client.returns(upstream("linear", "fallback", points));

        Map<String, Object> result = service.forecast(ACTOR, "ect", 60);

        assertThat(result.get("status")).isEqualTo("ok");
        assertThat(result.get("kind")).isEqualTo("statistical");
        assertThat(result.get("mode")).isEqualTo("linear");
        assertThat(result.get("steps")).isEqualTo(2);          // 60s / 30s
        assertThat(result.get("sampleCount")).isEqualTo(40);
        assertThat((List<?>) result.get("series")).hasSize(40);
        List<Map<String, Object>> forecast = (List<Map<String, Object>>) result.get("forecast");
        assertThat(forecast).hasSize(2);
        assertThat(forecast.get(0).get("h")).isEqualTo(1);
        assertThat(forecast.get(0).get("t")).isEqualTo(30L);
        assertThat(forecast.get(0).get("median")).isEqualTo(120d);
        assertThat(forecast.get(0).get("p10")).isEqualTo(110d);
        assertThat(forecast.get(0).get("p90")).isEqualTo(130d);
        // 传给上游的 horizon 是步数，不是秒
        assertThat(client.lastPayload.get("horizon")).isEqualTo(2);
        assertThat(client.lastPayload.get("metric_name")).isEqualTo("cpu");
        assertThat((List<?>) client.lastPayload.get("values")).hasSize(40);
    }

    @Test
    @DisplayName("统计降级被如实标注，绝不写成 PatchTST/MLP+GRU")
    void statisticalFallbackIsHonest() {
        seed(1, "cpu", 40, 30, 40d);
        client.returns(upstream("linear", "fallback", List.of(point(1, 90, 80, 100))));

        Map<String, Object> result = service.forecast(ACTOR, "ect", 30);

        assertThat(result.get("kind")).isEqualTo("statistical");
        assertThat(String.valueOf(result.get("note"))).contains("统计降级");
        Map<String, Object> model = (Map<String, Object>) result.get("model");
        assertThat(model.get("version")).isEqualTo("statistical-baseline");
        assertThat(model.get("gate")).isEqualTo("FALLBACK");
        assertThat((Map<String, Object>) model.get("metrics")).containsEntry("mae", null);
    }

    @Test
    @DisplayName("上游宣称 PatchTST 成功时才标记 neural")
    void neuralOnlyWhenUpstreamConfirms() {
        seed(1, "cpu", 40, 30, 40d);
        client.returns(upstream("patchtst", "ok", List.of(point(1, 90, 80, 100))));

        Map<String, Object> result = service.forecast(ACTOR, "ect", 30);

        assertThat(result.get("kind")).isEqualTo("neural");
    }

    @Test
    @DisplayName("采样点不足：unavailable，不补合成曲线")
    void insufficientSamplesAreUnavailable() {
        seed(1, "cpu", 5, 30, 40d);

        Map<String, Object> result = service.forecast(ACTOR, "ect", 30);

        assertThat(result.get("status")).isEqualTo("unavailable");
        assertThat(result.get("kind")).isEqualTo("unavailable");
        assertThat((List<?>) result.get("forecast")).isEmpty();
        assertThat((List<?>) result.get("series")).isEmpty();
        assertThat(String.valueOf(result.get("note"))).contains("offline");
    }

    @Test
    @DisplayName("上游不可达：fail-soft 成 unavailable，不抛异常")
    void upstreamFailureIsFailSoft() {
        seed(1, "cpu", 40, 30, 40d);
        client.next = Optional.empty();

        Map<String, Object> result = service.forecast(ACTOR, "ect", 30);

        assertThat(result.get("status")).isEqualTo("unavailable");
        assertThat(String.valueOf(result.get("modelStatusDetail"))).contains("不可达");
    }

    @Test
    @DisplayName("租户隔离：不读其他用户的采样")
    void tenantIsolationOnSamples() {
        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,template_id,enabled) "
                + "VALUES(2,2,'other','system','ssh://other',60,NULL,1)");
        seed(2, "cpu", 40, 30, 40d);

        Map<String, Object> catalog = service.catalog(1L);
        assertThat((List<?>) catalog.get("slots")).isEmpty();

        Map<String, Object> result = service.forecast(ACTOR, "ect", 30);
        assertThat(result.get("status")).isEqualTo("unavailable");
    }

    @Test
    @DisplayName("越界预测：只在越过槽位阈值时产生，且同一档只记最早一次")
    void crossingsRespectDeclaredThresholds() {
        seed(1, "cpu", 20, 30, 40d);
        List<Map<String, Object>> points = new ArrayList<>();
        points.add(point(1, 96, 90, 100));   // 超 crit 95
        points.add(point(2, 99, 90, 100));
        client.returns(upstream("linear", "fallback", points));

        Map<String, Object> result = service.forecast(ACTOR, "ect", 60);

        List<Map<String, Object>> crossings = (List<Map<String, Object>>) result.get("crossings");
        assertThat(crossings).hasSize(1);
        assertThat(crossings.get(0).get("kind")).isEqualTo("crit");
        assertThat(crossings.get(0).get("step")).isEqualTo(1);
        assertThat(crossings.get(0).get("h")).isEqualTo(30);
        assertThat(crossings.get(0).get("confidence")).isNotNull();
    }

    @Test
    @DisplayName("resolveKind：只有 model_status=ok 且 mode=patchtst 才是 neural")
    void resolveKindMapping() {
        assertThat(SentinelForecastClient.resolveKind("patchtst", "ok")).isEqualTo("neural");
        assertThat(SentinelForecastClient.resolveKind("linear", "ok")).isEqualTo("statistical");
        assertThat(SentinelForecastClient.resolveKind("linear", "fallback")).isEqualTo("statistical");
        assertThat(SentinelForecastClient.resolveKind(null, "fallback")).isEqualTo("unavailable");
        assertThat(SentinelForecastClient.resolveKind("weird", "broken")).isEqualTo("unavailable");
    }
}
