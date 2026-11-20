package com.smartops.controller;

import com.smartops.config.SecurityConfig;
import com.smartops.security.InternalTokenAuthenticationFilter;
import com.smartops.service.AgentTriggerService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Map;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * W7 内部触发端点的门禁：浏览器会话不能代替内部身份，参数按 alertId 透传。
 */
@WebMvcTest(InternalAgentTriggerController.class)
@Import({SecurityConfig.class, InternalTokenAuthenticationFilter.class})
@TestPropertySource(properties = {
        "smartops.security.internal-token=test-internal-token",
        "smartops.security.internal-bypass=false"
})
class InternalAgentTriggerControllerTest {

    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;
    @MockBean private com.smartops.security.AdminMfaService mfa;
    @MockBean private AgentTriggerService service;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void triggerWithoutInternalTokenReturns401() throws Exception {
        mockMvc.perform(post("/api/internal/agent/trigger")
                        .contentType("application/json")
                        .content("{\"alertId\":42}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void triggerWithWrongTokenReturns403() throws Exception {
        mockMvc.perform(post("/api/internal/agent/trigger")
                        .header("X-SmartOps-Internal-Token", "wrong")
                        .contentType("application/json")
                        .content("{\"alertId\":42}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void triggerWithInternalTokenPassesAlertId() throws Exception {
        when(service.trigger(eq(42L)))
                .thenReturn(Map.of("triggered", true, "resourceKey", "task:7"));

        mockMvc.perform(post("/api/internal/agent/trigger")
                        .header("X-SmartOps-Internal-Token", "test-internal-token")
                        .contentType("application/json")
                        .content("{\"alertId\":42}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.triggered").value(true))
                .andExpect(jsonPath("$.data.resourceKey").value("task:7"));

        verify(service).trigger(42L);
    }
}
