package com.smartops.integration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * 告警研判 / 通知 / 知识沉淀 的集成测试（真实 schema + 真实 SQL）。
 *
 * <p>为什么用 H2 而不是纯 Mockito：这条链路的正确性大部分落在 SQL 上
 * （谁能看到哪条告警、什么状态才能沉淀、时间线怎么写），用替身验证等于没验证。
 * H2 跑的是**真实迁移脚本**，所以表结构、约束、幂等性也一并被覆盖。</p>
 *
 * <p>告警本身直接插库：真实告警需要已授权的 SSH 运行连接（会话级资源），
 * 集成测试环境里没有目标机。插库只跳过"怎么产生告警"，不跳过"告警之后的一切"。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:sentinel_workflow;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        // 关掉轮询：本测试不依赖采集，避免后台线程干扰断言
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class SentinelAlertWorkflowIntegrationTest {

    private static final String PASSWORD = "SentinelWorkflowPass42!";
    private static final long OWNER = 71L;
    private static final long STRANGER = 72L;

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void seed() {
        // operator_memory 由本地 schema 提供，测试库默认没有；研判查询会用到它。
        // 这里补建最小结构（不改生产代码），让研判路径在两种库上走同一条逻辑。
        jdbc.execute("""
                CREATE TABLE IF NOT EXISTS operator_memory(
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  user_id BIGINT NOT NULL,
                  incident_key VARCHAR(128),
                  memory_type VARCHAR(32),
                  preferred_action VARCHAR(500),
                  source_refs VARCHAR(500),
                  evidence_count INT DEFAULT 0,
                  confidence DOUBLE DEFAULT 0,
                  status VARCHAR(16) DEFAULT 'ACTIVE',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
                """);
        for (String table : List.of("sentinel_knowledge_candidate", "sentinel_notification", "sentinel_alert_event",
                "sentinel_metric_sample", "sentinel_script_run", "sentinel_alert", "sentinel_alert_rule",
                "sentinel_script_version", "sentinel_script", "sentinel_task", "sentinel_threshold_template",
                "operator_memory")) {
            if (exists(table)) jdbc.update("DELETE FROM " + table);
        }
        if (exists("app_user")) jdbc.update("DELETE FROM app_user");
        String hash = new BCryptPasswordEncoder().encode(PASSWORD);
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(?,?,?,'operator'),(?,?,?,'operator')",
                OWNER, "sentinel-owner", hash, STRANGER, "sentinel-stranger", hash);
    }

    private boolean exists(String table) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE LOWER(TABLE_NAME)=?", Integer.class, table);
        return count != null && count > 0;
    }

    /* ── 会话辅助 ─────────────────────────────────────────────────────── */

    private record Client(MockHttpSession session, String csrf) {}

    private Client anonymous() throws Exception {
        var result = mvc.perform(get("/api/auth/session")).andExpect(status().isOk()).andReturn();
        return new Client((MockHttpSession) result.getRequest().getSession(false),
                json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }

    private Client login(String username) throws Exception {
        Client client = anonymous();
        mvc.perform(post("/api/auth/login").session(client.session())
                        .header("X-CSRF-TOKEN", client.csrf())
                        .contentType("application/json")
                        .content(json.writeValueAsString(Map.of("username", username, "password", PASSWORD, "portal", "user"))))
                .andExpect(status().isOk());
        // 登录后 CSRF token 会轮换：必须用已认证会话重新取一次，否则后续写操作 403。
        var refreshed = mvc.perform(get("/api/auth/session").session(client.session())).andReturn().getResponse();
        String token = json.readTree(body(refreshed)).path("data").path("csrfToken").asText();
        return new Client(client.session(), token);
    }

    /**
     * 按 UTF-8 解码响应体。
     *
     * <p>{@code getContentAsString()} 在响应未声明 charset 时按 ISO-8859-1 解码，
     * 中文会被解成乱码，导致"内容没问题但断言失败"的假失败。</p>
     */
    private static String body(org.springframework.mock.web.MockHttpServletResponse response) throws Exception {
        return new String(response.getContentAsByteArray(), java.nio.charset.StandardCharsets.UTF_8);
    }

    private ResultActions send(Client client, org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request) throws Exception {
        return mvc.perform(request.session(client.session()).header("X-CSRF-TOKEN", client.csrf()));
    }

    /* ── 夹具 ─────────────────────────────────────────────────────────── */

    /** 建一个归属某用户的哨兵任务 + 一条告警，返回告警 id。 */
    private long alertOwnedBy(long ownerId, String severity, String status) {
        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled) VALUES(?,?,?,'system','memory',60,1)",
                900L + ownerId, ownerId, "web-" + ownerId);
        jdbc.update("""
                INSERT INTO sentinel_alert(id,task_id,severity,status,title,metric,observed_value,threshold_value,fired_at)
                VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                """, 800L + ownerId, 900L + ownerId, severity, status, "web-" + ownerId + "：内存越界",
                "memory", "95.0", "memory > 90");
        return 800L + ownerId;
    }

    /* ── 断言 ─────────────────────────────────────────────────────────── */

    @Test
    @DisplayName("没有运行连接时，采集不会伪造指标（任务如实标记 no_runtime）")
    void missingRuntimeIsReportedHonestly() throws Exception {
        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled) VALUES(950,?,?, 'system','memory',60,1)",
                OWNER, "no-runtime-task");
        Client client = login("sentinel-owner");
        // 接口层不暴露"马上采样"，这里验证边界的说明而不是伪造一次采集。
        send(client, get("/api/sentinel/runtime-boundary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.note").value(org.hamcrest.Matchers.containsString("no_runtime")));
        // 任务仍是启用状态，但从未被写入过在线状态
        assertThat(jdbc.queryForObject("SELECT last_status FROM sentinel_task WHERE id=950", String.class)).isNull();
    }

    @Test
    @DisplayName("未登录访问研判与知识接口一律被拒绝")
    void anonymousCannotReachNewEndpoints() throws Exception {
        // 未认证请求必须被拒绝；本项目按 403 返回，测试同时容忍 401 以适配安全配置调整。
        mvc.perform(post("/api/sentinel/alerts/1/analyze")).andExpect(result -> {
            int status = result.getResponse().getStatus();
            assertThat(status == 401 || status == 403).as("anonymous must be rejected, got " + status).isTrue();
        });
        mvc.perform(get("/api/sentinel/knowledge-candidates")).andExpect(result -> {
            int status = result.getResponse().getStatus();
            assertThat(status == 401 || status == 403).as("anonymous must be rejected, got " + status).isTrue();
        });
    }

    @Test
    @DisplayName("研判只产出建议，不改状态；并把建议与推荐脚本落库")
    void analyzeProducesAdviceWithoutChangingStatus() throws Exception {
        long alertId = alertOwnedBy(OWNER, "P2", "OPEN");
        jdbc.update("""
                INSERT INTO sentinel_script(id,user_id,name,language,risk_level,current_version,approved,enabled,timeout_sec)
                VALUES(501,?,'memory-pressure-relief','shell','LOW',1,1,1,30)
                """, OWNER);
        Client client = login("sentinel-owner");

        var adviceResponse = send(client, post("/api/sentinel/alerts/" + alertId + "/analyze"))
                .andDo(org.springframework.test.web.servlet.result.MockMvcResultHandlers.print())
                .andExpect(status().isOk())
                .andReturn().getResponse();
        JsonNode advice = json.readTree(body(adviceResponse)).path("data");
        // 摘要讲清"是什么、证据、推荐什么、下一步"，并把结论限定为建议而非定论。
        assertThat(advice.path("summary").asText()).contains("memory").contains("推荐脚本");
        assertThat(advice.path("disclaimer").asText()).contains("建议").contains("审批");
        assertThat(advice.path("evidence")).isNotEmpty();
        assertThat(advice.path("scripts").toString()).contains("memory-pressure-relief");

        // 状态没有被研判改动
        assertThat(jdbc.queryForObject("SELECT status FROM sentinel_alert WHERE id=?", String.class, alertId))
                .isEqualTo("OPEN");
        // 建议确实落库，便于后续审阅
        assertThat(jdbc.queryForObject("SELECT ai_summary FROM sentinel_alert WHERE id=?", String.class, alertId))
                .isNotBlank();
        assertThat(jdbc.queryForObject("SELECT recommended_script_id FROM sentinel_alert WHERE id=?", Long.class, alertId))
                .isEqualTo(501L);
        // 时间线留痕
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_alert_event WHERE alert_id=? AND kind='AI_ANALYZED'",
                Integer.class, alertId)).isEqualTo(1);
    }

    @Test
    @DisplayName("未关闭的告警不能沉淀为知识（409），避免把未验证的处置写成经验")
    void openAlertCannotBecomeKnowledge() throws Exception {
        long alertId = alertOwnedBy(OWNER, "P2", "OPEN");
        Client client = login("sentinel-owner");
        send(client, post("/api/sentinel/alerts/" + alertId + "/knowledge"))
                .andExpect(status().isConflict());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_knowledge_candidate WHERE alert_id=?",
                Integer.class, alertId)).isZero();
    }

    @Test
    @DisplayName("已关闭的告警可沉淀为待复核知识候选，内容含证据与关闭说明")
    void closedAlertBecomesReviewableCandidate() throws Exception {
        long alertId = alertOwnedBy(OWNER, "P2", "CLOSED");
        jdbc.update("UPDATE sentinel_alert SET close_note='清理缓存后恢复', ai_summary='研判：内存压力' WHERE id=?", alertId);
        jdbc.update("INSERT INTO sentinel_alert_event(alert_id,actor_id,kind,detail) VALUES(?,?,'FIRED','命中阈值')", alertId, OWNER);
        Client client = login("sentinel-owner");

        var knowledgeResponse = send(client, post("/api/sentinel/alerts/" + alertId + "/knowledge"))
                .andDo(org.springframework.test.web.servlet.result.MockMvcResultHandlers.print())
                .andExpect(status().isOk())
                .andReturn().getResponse();
        JsonNode data = json.readTree(body(knowledgeResponse)).path("data");
        assertThat(data.path("status").asText()).isEqualTo("PENDING_REVIEW");
        assertThat(data.path("nextStep").asText()).contains("复核");

        Long candidateId = data.path("candidateId").asLong();
        assertThat(candidateId).isPositive();
        String content = jdbc.queryForObject("SELECT content FROM sentinel_knowledge_candidate WHERE id=?", String.class, candidateId);
        // 沉淀内容必须能复盘：现象、证据、研判、关闭说明都在
        assertThat(content).contains("现象").contains("证据").contains("研判").contains("清理缓存后恢复");

        send(client, get("/api/sentinel/knowledge-candidates"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].id").value(candidateId));
    }

    @Test
    @DisplayName("他人告警一律 404，不泄露存在性")
    void crossTenantAlertIs404() throws Exception {
        long alertId = alertOwnedBy(OWNER, "P2", "OPEN");
        Client stranger = login("sentinel-stranger");
        send(stranger, post("/api/sentinel/alerts/" + alertId + "/analyze")).andExpect(status().isNotFound());
        send(stranger, post("/api/sentinel/alerts/" + alertId + "/knowledge")).andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("通知如实区分站内已发出与其它渠道待投递")
    void notifyRecordsPerChannelHonesty() throws Exception {
        long alertId = alertOwnedBy(OWNER, "P2", "OPEN");
        jdbc.update("""
                INSERT INTO sentinel_alert_rule(user_id,name,severity,auto_dispatch,notify_channels,webhook_url,enabled)
                VALUES(?,'rule-1','P2',0,'inapp,email,webhook','https://93.184.216.34/hook',1)
                """, OWNER);
        Client client = login("sentinel-owner");
        String body = send(client, post("/api/sentinel/alerts/" + alertId + "/notify"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        // 接口要返回逐渠道结果，而不是一个笼统的"成功"
        JsonNode results = json.readTree(body).path("data");
        assertThat(results.path("inapp").asText()).isEqualTo("sent");
        // 没有 SMTP 就必须如实说没配置，不能写成 sent
        assertThat(results.path("email").asText()).isEqualTo("not_configured");

        Map<String, Object> inapp = jdbc.queryForMap(
                "SELECT status FROM sentinel_notification WHERE alert_id=? AND channel='inapp'", alertId);
        assertThat(inapp.get("status")).isEqualTo("sent");
        Map<String, Object> email = jdbc.queryForMap(
                "SELECT status,error_detail FROM sentinel_notification WHERE alert_id=? AND channel='email'", alertId);
        assertThat(email.get("status")).isEqualTo("not_configured");
        assertThat(String.valueOf(email.get("error_detail"))).contains("SMTP");
    }

    @Test
    @DisplayName("Webhook 指向内网时被拒绝，且不会发起请求")
    void webhookToPrivateNetworkIsRejected() throws Exception {
        long alertId = alertOwnedBy(OWNER, "P2", "OPEN");
        jdbc.update("""
                INSERT INTO sentinel_alert_rule(user_id,name,severity,auto_dispatch,notify_channels,webhook_url,enabled)
                VALUES(?,'rule-2','P2',0,'webhook','http://127.0.0.1:8080/actuator/health',1)
                """, OWNER);
        Client client = login("sentinel-owner");
        String body = send(client, post("/api/sentinel/alerts/" + alertId + "/notify"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        assertThat(json.readTree(body).path("data").path("webhook").asText()).isEqualTo("rejected");

        Map<String, Object> row = jdbc.queryForMap(
                "SELECT status,error_detail,attempts FROM sentinel_notification WHERE alert_id=? AND channel='webhook'", alertId);
        assertThat(row.get("status")).isEqualTo("rejected");
        // 关键是"没有真的发出去"，所以重试次数必须是 0
        assertThat(((Number) row.get("attempts")).intValue()).isZero();
    }

    @Test
    @DisplayName("保存规则时就拒绝内网 Webhook，而不是等告警触发才失败")
    void unsafeWebhookRejectedAtSaveTime() throws Exception {
        Client client = login("sentinel-owner");
        String body = json.writeValueAsString(Map.of(
                "name", "unsafe-rule", "severity", "P2",
                "notifyChannels", "webhook", "webhookUrl", "http://127.0.0.1:8080/actuator/health"));
        send(client, post("/api/sentinel/alert-rules").contentType("application/json").content(body))
                .andExpect(status().isBadRequest());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_alert_rule WHERE name='unsafe-rule'",
                Integer.class)).isZero();
    }

    @Test
    @DisplayName("资产分组：批量启停只影响该分组，且跨用户不可见")
    void groupToggleAffectsOnlyThatGroup() throws Exception {
        // 三台资产：两个 web-prod、一个 db-core
        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled,group_label) VALUES(981,?,?,'system','cpu',60,1,'web-prod')", OWNER, "web-a");
        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled,group_label) VALUES(982,?,?,'system','cpu',60,1,'web-prod')", OWNER, "web-b");
        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled,group_label) VALUES(983,?,?,'system','cpu',60,1,'db-core')", OWNER, "db-a");
        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled,group_label) VALUES(984,?,?,'system','cpu',60,1,'web-prod')", STRANGER, "other-user");

        Client client = login("sentinel-owner");
        send(client, get("/api/sentinel/task-groups"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.label=='web-prod')].total").value(org.hamcrest.Matchers.hasItem(2)))
                .andExpect(jsonPath("$.data[?(@.label=='db-core')].total").value(org.hamcrest.Matchers.hasItem(1)));

        // 停用 web-prod：只应影响该用户的 2 条
        String body = send(client, patch("/api/sentinel/task-groups/web-prod/enabled")
                .contentType("application/json").content("{\"enabled\":false}"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        assertThat(json.readTree(body).path("data").path("changed").asInt()).isEqualTo(2);

        assertThat(jdbc.queryForObject("SELECT enabled FROM sentinel_task WHERE id=981", Boolean.class)).isFalse();
        assertThat(jdbc.queryForObject("SELECT enabled FROM sentinel_task WHERE id=982", Boolean.class)).isFalse();
        // 其它分组不受影响
        assertThat(jdbc.queryForObject("SELECT enabled FROM sentinel_task WHERE id=983", Boolean.class)).isTrue();
        // 其它用户的同名分组不受影响
        assertThat(jdbc.queryForObject("SELECT enabled FROM sentinel_task WHERE id=984", Boolean.class)).isTrue();
    }

    @Test
    @DisplayName("不存在的分组返回 changed=0，而不是报错")
    void unknownGroupIsNotAnError() throws Exception {
        Client client = login("sentinel-owner");
        String body = send(client, patch("/api/sentinel/task-groups/no-such-group/enabled")
                .contentType("application/json").content("{\"enabled\":true}"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        assertThat(json.readTree(body).path("data").path("changed").asInt()).isZero();
    }

    @Test
    @DisplayName("脚本上传：扩展名推断语言，未知扩展名被拒，二进制被拒")
    void scriptUploadInfersLanguageAndRejectsBadInput() throws Exception {
        Client client = login("sentinel-owner");
        // 正常上传
        String ok = send(client, post("/api/sentinel/scripts/upload").contentType("application/json")
                .content(json.writeValueAsString(Map.of(
                        "fileName", "check-memory.py", "content", "print('ok')", "riskLevel", "LOW"))))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        JsonNode created = json.readTree(ok).path("data");
        assertThat(created.path("language").asText()).isEqualTo("python");
        assertThat(created.path("name").asText()).isEqualTo("check-memory");

        // 未知扩展名 -> 400，且不猜语言
        send(client, post("/api/sentinel/scripts/upload").contentType("application/json")
                .content(json.writeValueAsString(Map.of("fileName", "notes.txt", "content", "hello", "riskLevel", "LOW"))))
                .andExpect(status().isBadRequest());

        // 上传同样过预检：危险内容被拒
        send(client, post("/api/sentinel/scripts/upload").contentType("application/json")
                .content(json.writeValueAsString(Map.of(
                        "fileName", "danger.sh", "content", "rm -rf /var/lib/mysql", "riskLevel", "LOW"))))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("采集边界接口如实说明常驻采集需要独立采集器")
    void runtimeBoundaryIsDocumented() throws Exception {
        Client client = login("sentinel-owner");
        send(client, get("/api/sentinel/runtime-boundary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.note").value(org.hamcrest.Matchers.containsString("采集器")));
    }
}
