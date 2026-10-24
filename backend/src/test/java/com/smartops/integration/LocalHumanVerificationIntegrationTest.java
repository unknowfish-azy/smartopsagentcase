package com.smartops.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static com.smartops.security.LocalScene.shapes;
import static com.smartops.security.LocalScene.solution;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * 未配置任何 Turnstile 密钥时，人机验证必须真的能在离线状态工作：
 * 策略下发图形场景 → 提交点击坐标换取一次性 token → 该 token 继续用于强制的注册/管理员登录流程。
 */
@SpringBootTest(properties = {
        "smartops.security.human-verification.enabled=true",
        "smartops.security.human-verification.site-key=",
        "smartops.security.human-verification.secret-key=",
        "smartops.security.human-verification.hostnames=",
        // 集成测试不模拟人类点击耗时，把"最短作答时间"门槛设为 0；该门槛本身由单元测试用可推进时钟覆盖。
        "smartops.security.human-verification.min-response-ms=0"
})
@AutoConfigureMockMvc
@ActiveProfiles("test")
class LocalHumanVerificationIntegrationTest {
    @Autowired MockMvc mvc;
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void unconfiguredTurnstileServesARealSvgChallengeWithoutGeometryOfTheAnswer() throws Exception {
        var policyResponse = mvc.perform(get("/api/auth/human-verification").param("action", "register"))
                .andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.data.enabled").value(true))
                .andExpect(jsonPath("$.data.available").value(true))
                .andExpect(jsonPath("$.data.provider").value("local"))
                .andExpect(jsonPath("$.data.required").value(true))
                .andExpect(jsonPath("$.data.siteKey").value(""))
                .andReturn().getResponse();
        var policy = json(policyResponse).path("data");
        assertTrue(policy.path("scene").asText().contains("<svg"), "必须下发服务端生成的图形场景");
        assertFalse(policy.path("scene").asText().contains("data-"), "场景不得携带答案属性");
        assertFalse(policy.path("scene").asText().contains("target"), "场景不得给出目标对应关系");
        assertTrue(policy.path("targets").asInt() >= 1);
        assertTrue(policy.path("tolerance").asInt() > 0);
        assertFalse(policy.path("prompt").asText().isBlank(), "必须给出点选提示");
        assertEquals(policy.path("targets").asInt(), solution(policy.path("prompt").asText(), shapes(policy.path("scene").asText())).size(),
                "提示必须唯一指向 targets 个图形，实际提示：" + policy.path("prompt").asText()
                        + " 场景：" + policy.path("scene").asText());
        assertFalse(policy.path("challenge").asText().isBlank());
    }

    @Test
    void clicksExchangeForATokenThatIsSingleUseWithinTheSameSession() throws Exception {
        var session = (MockHttpSession) mvc.perform(get("/api/auth/session")).andReturn().getRequest().getSession(false);
        var policy = policy(session, "register");
        String nonce = policy.path("challenge").asText();
        var clicks = solution(policy.path("prompt").asText(), shapes(policy.path("scene").asText()));

        var proofResponse = mvc.perform(post("/api/auth/human-verification/verify").session(session).contentType("application/json")
                        .content("{\"action\":\"register\",\"nonce\":\"" + nonce + "\",\"clicks\":" + json(clicks) + "}"))
                .andReturn().getResponse();
        assertTrue(proofResponse.getHeader("Cache-Control") != null && proofResponse.getHeader("Cache-Control").contains("no-store"),
                "验证接口必须不可缓存：" + proofResponse.getHeader("Cache-Control"));
        var proofBody = json(proofResponse);
        assertEquals(200, proofResponse.getStatus(), "body=" + proofBody
                + " prompt=" + policy.path("prompt").asText()
                + " scene=" + policy.path("scene").asText()
                + " clicks=" + json(clicks));
        String token = proofBody.path("data").path("token").asText();
        assertFalse(token.isBlank());
        assertEquals(clicks.size(), proofBody.path("data").path("targets").asInt());
        assertTrue(token.startsWith("local.1." + nonce + "."), "token 必须绑定同一个会话挑战与点击坐标");

        mvc.perform(post("/api/auth/human-verification/verify").session(session).contentType("application/json")
                        .content("{\"action\":\"register\",\"nonce\":\"" + nonce + "\",\"clicks\":" + json(clicks) + "}"))
                .andExpect(status().is(428));

        // 拿到的 token 不能绕过 CSRF：注册接口依然要求安全令牌。
        mvc.perform(post("/api/auth/register").session(session).contentType("application/json")
                        .content("{\"username\":\"offlinehuman\",\"password\":\"LongPassword123!\",\"confirmPassword\":\"LongPassword123!\",\"humanToken\":\"" + token + "\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongClicksOnARealChallengeAreRejected() throws Exception {
        var session = (MockHttpSession) mvc.perform(get("/api/auth/session")).andReturn().getRequest().getSession(false);
        var policy = policy(session, "admin_login");
        // (0,0) 必然落在所有图形容差之外：图形中心的坐标下限是 36。
        mvc.perform(post("/api/auth/human-verification/verify").session(session).contentType("application/json")
                        .content("{\"action\":\"admin_login\",\"nonce\":\"" + policy.path("challenge").asText() + "\",\"clicks\":[{\"x\":0,\"y\":0}]}"))
                .andExpect(status().is(428));
    }

    @Test
    void unknownActionIsRejectedAsABadRequest() throws Exception {
        var session = (MockHttpSession) mvc.perform(get("/api/auth/session")).andReturn().getRequest().getSession(false);
        var policy = policy(session, "admin_login");
        mvc.perform(post("/api/auth/human-verification/verify").session(session).contentType("application/json")
                        .content("{\"action\":\"unknown\",\"nonce\":\"" + policy.path("challenge").asText() + "\",\"clicks\":[{\"x\":10,\"y\":10}]}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void emptyClicksAndOutOfRangeCoordinatesAreRejectedAsBadRequests() throws Exception {
        var emptySession = (MockHttpSession) mvc.perform(get("/api/auth/session")).andReturn().getRequest().getSession(false);
        var emptyPolicy = policy(emptySession, "admin_login");
        mvc.perform(post("/api/auth/human-verification/verify").session(emptySession).contentType("application/json")
                        .content("{\"action\":\"admin_login\",\"nonce\":\"" + emptyPolicy.path("challenge").asText() + "\",\"clicks\":[]}"))
                .andExpect(status().isBadRequest());

        var rangeSession = (MockHttpSession) mvc.perform(get("/api/auth/session")).andReturn().getRequest().getSession(false);
        var rangePolicy = policy(rangeSession, "admin_login");
        mvc.perform(post("/api/auth/human-verification/verify").session(rangeSession).contentType("application/json")
                        .content("{\"action\":\"admin_login\",\"nonce\":\"" + rangePolicy.path("challenge").asText() + "\",\"clicks\":[{\"x\":999,\"y\":999}]}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void mandatoryPortalsStillDemandVerificationWithoutAToken() throws Exception {
        mvc.perform(get("/api/auth/human-verification").param("action", "admin_login"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.required").value(true))
                .andExpect(jsonPath("$.data.provider").value("local"));
        var sessionResult = mvc.perform(get("/api/auth/session")).andReturn();
        var session = (MockHttpSession) sessionResult.getRequest().getSession(false);
        var csrf = mapper.readTree(sessionResult.getResponse().getContentAsString()).path("data").path("csrfToken").asText();
        mvc.perform(post("/api/auth/login").session(session).header("X-CSRF-TOKEN", csrf).contentType("application/json")
                        .content("{\"username\":\"admin\",\"password\":\"invalid-password\",\"portal\":\"admin\"}"))
                .andExpect(status().is(428));
    }

    private com.fasterxml.jackson.databind.JsonNode policy(MockHttpSession session, String action) throws Exception {
        return json(mvc.perform(get("/api/auth/human-verification").session(session).param("action", action))
                .andExpect(status().isOk()).andReturn().getResponse()).path("data");
    }

    /** 直接按 UTF-8 解码响应字节：MockHttpServletResponse.getContentAsString() 会用 servlet 默认字符集，中文提示会被破坏。 */
    private com.fasterxml.jackson.databind.JsonNode json(org.springframework.mock.web.MockHttpServletResponse response) throws Exception {
        return mapper.readTree(new String(response.getContentAsByteArray(), java.nio.charset.StandardCharsets.UTF_8));
    }

    private static String json(List<int[]> clicks) {
        StringBuilder body = new StringBuilder("[");
        for (int index = 0; index < clicks.size(); index++) {
            if (index > 0) body.append(',');
            body.append("{\"x\":").append(clicks.get(index)[0]).append(",\"y\":").append(clicks.get(index)[1]).append('}');
        }
        return body.append(']').toString();
    }
}
