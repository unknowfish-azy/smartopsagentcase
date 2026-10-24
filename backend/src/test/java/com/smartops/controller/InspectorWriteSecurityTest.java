package com.smartops.controller;

import com.smartops.config.SecurityConfig;
import com.smartops.security.InternalTokenAuthenticationFilter;
import com.smartops.service.InspectorEventService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InspectorController.class)
@Import({SecurityConfig.class, InternalTokenAuthenticationFilter.class})
@TestPropertySource(properties = {
        "smartops.security.internal-token=test-internal-token",
        "smartops.security.internal-bypass=false"
})
class InspectorWriteSecurityTest {
    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;
    @MockBean private com.smartops.security.AdminMfaService mfa;

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private InspectorEventService service;

    @Test
    void writeWithoutInternalTokenReturns401() throws Exception {
        mockMvc.perform(post("/api/inspector/check")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void writeWithInternalTokenReachesController() throws Exception {
        when(service.record(any())).thenReturn(java.util.Map.of());
        String body = "{\"taskId\":\"TASK-1\",\"status\":\"PASS\","
                + "\"severity\":\"INFO\",\"reason\":\"ok\"}";

        mockMvc.perform(post("/api/inspector/check")
                        .header("X-SmartOps-Internal-Token", "test-internal-token")
                        .contentType("application/json")
                        .content(body))
                .andExpect(status().isOk());
    }
}
