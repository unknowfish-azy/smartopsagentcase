package com.smartops.controller;

import com.smartops.config.SecurityConfig;
import com.smartops.recovery.RecoveryContractService;
import com.smartops.security.InternalTokenAuthenticationFilter;
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

/**
 * 恢复契约内部写入端点的门禁：浏览器会话不能代替内部身份。
 *
 * <p>与 InspectorWriteSecurityTest 同一套过滤器链路，只验证"谁能进来"，
 * 语义校验在 RecoveryContractIntegrationTest 里覆盖。</p>
 */
@WebMvcTest(InternalRecoveryController.class)
@Import({SecurityConfig.class, InternalTokenAuthenticationFilter.class})
@TestPropertySource(properties = {
        "smartops.security.internal-token=test-internal-token",
        "smartops.security.internal-bypass=false"
})
class RecoveryContractSecurityTest {

    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;
    @MockBean private com.smartops.security.AdminMfaService mfa;
    @MockBean private RecoveryContractService service;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void writeWithoutInternalTokenReturns401() throws Exception {
        mockMvc.perform(post("/api/internal/recovery/contracts")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void writeWithWrongTokenReturns403() throws Exception {
        mockMvc.perform(post("/api/internal/recovery/contracts")
                        .header("X-SmartOps-Internal-Token", "wrong")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void writeWithInternalTokenReachesController() throws Exception {
        when(service.create(any())).thenReturn(java.util.Map.of("id", 1L));

        mockMvc.perform(post("/api/internal/recovery/contracts")
                        .header("X-SmartOps-Internal-Token", "test-internal-token")
                        .contentType("application/json")
                        .content("{\"ownerUserId\":81,\"runId\":1,\"idempotencyKey\":\"k\","
                                + "\"contract\":{},\"claim\":{}}"))
                .andExpect(status().isOk());
    }
}
