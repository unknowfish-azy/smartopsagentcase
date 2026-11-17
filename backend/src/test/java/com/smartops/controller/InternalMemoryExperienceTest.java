package com.smartops.controller;

import com.smartops.config.SecurityConfig;
import com.smartops.security.InternalTokenAuthenticationFilter;
import com.smartops.service.OperatorMemoryService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 复盘沉淀内部端点的门禁与透传：浏览器会话不能代替内部身份。
 *
 * <p>与 RecoveryContractSecurityTest 同一套过滤器链路，只验证"谁能进来、参数是否透传"，
 * recordLearned 的幂等与置信度逻辑在 OperatorMemoryServiceTest 里覆盖。</p>
 */
@WebMvcTest(InternalMemoryController.class)
@Import({SecurityConfig.class, InternalTokenAuthenticationFilter.class})
@TestPropertySource(properties = {
        "smartops.security.internal-token=test-internal-token",
        "smartops.security.internal-bypass=false"
})
class InternalMemoryExperienceTest {

    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;
    @MockBean private com.smartops.security.AdminMfaService mfa;
    @MockBean private OperatorMemoryService service;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void writeWithoutInternalTokenReturns401() throws Exception {
        mockMvc.perform(post("/api/internal/memory/experience")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void writeWithWrongTokenReturns403() throws Exception {
        mockMvc.perform(post("/api/internal/memory/experience")
                        .header("X-SmartOps-Internal-Token", "wrong")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void writeWithInternalTokenPassesArgumentsToService() throws Exception {
        mockMvc.perform(post("/api/internal/memory/experience")
                        .header("X-SmartOps-Internal-Token", "test-internal-token")
                        .contentType("application/json")
                        .content("{\"userId\":81,\"incidentKey\":\"nginx 502\","
                                + "\"preferredAction\":\"先查 upstream 日志\",\"sourceRefs\":\"PLAN_RUN:abc\"}"))
                .andExpect(status().isOk());
        verify(service).recordLearned(eq(81L), eq("nginx 502"), eq("先查 upstream 日志"), eq("PLAN_RUN:abc"));
    }

    @Test
    void missingUserIdSkipsService() throws Exception {
        mockMvc.perform(post("/api/internal/memory/experience")
                        .header("X-SmartOps-Internal-Token", "test-internal-token")
                        .contentType("application/json")
                        .content("{\"incidentKey\":\"nginx 502\"}"))
                .andExpect(status().isOk());
        verify(service, never()).recordLearned(org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString());
    }
}
