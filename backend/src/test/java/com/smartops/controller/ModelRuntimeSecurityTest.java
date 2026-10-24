package com.smartops.controller;

import com.smartops.dto.model.RuntimeModelConnectionResponse;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.dto.model.ModelConnectionResponse;
import com.smartops.config.SecurityConfig;
import com.smartops.config.CorsConfig;
import com.smartops.security.InternalTokenAuthenticationFilter;
import com.smartops.service.ModelConnectionService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.TestPropertySource;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.mockito.ArgumentMatchers.any;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ModelConnectionController.class)
@Import({SecurityConfig.class, CorsConfig.class, InternalTokenAuthenticationFilter.class})
@TestPropertySource(properties = {
        "smartops.security.internal-token=test-internal-token",
        "smartops.security.internal-bypass=false"
})
class ModelRuntimeSecurityTest {
    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;
    @MockBean private com.smartops.security.AdminMfaService mfa;
    @org.junit.jupiter.api.BeforeEach void validAccount() { when(accounts.isCurrent(any())).thenReturn(true); when(mfa.validSession(any(), any())).thenReturn(true); }
    private org.springframework.mock.web.MockHttpSession authenticatedSession() {
        var session = new org.springframework.mock.web.MockHttpSession();
        var user = new com.smartops.security.SessionUser(1L, "model-manager", "admin");
        var authentication = org.springframework.security.authentication.UsernamePasswordAuthenticationToken.authenticated(user, null,
                java.util.List.of(new org.springframework.security.core.authority.SimpleGrantedAuthority("ROLE_ADMIN")));
        session.setAttribute("SPRING_SECURITY_CONTEXT", new org.springframework.security.core.context.SecurityContextImpl(authentication));
        session.setAttribute("org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository.CSRF_TOKEN",
                new org.springframework.security.web.csrf.DefaultCsrfToken("X-CSRF-TOKEN", "_csrf", "test-csrf"));
        return session;
    }

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ModelConnectionService service;

    @Test
    void missingTokenReturns401() throws Exception {
        mockMvc.perform(get("/api/model-connections/1/runtime"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void localFrontendOriginsCanReachSaveValidation() throws Exception {
        for (String host : java.util.List.of("localhost", "127.0.0.1")) {
            for (int port = 5173; port <= 5176; port++) {
                mockMvc.perform(post("/api/model-connections")
                                .session(authenticatedSession()).header("X-CSRF-TOKEN", "test-csrf")
                                .header("Origin", "http://" + host + ":" + port)
                                .contentType("application/json").content("{}"))
                        .andExpect(status().isBadRequest())
                        .andExpect(jsonPath("$.code").value(400));
            }
        }
    }

    @Test
    void untrustedOriginCannotSaveConnection() throws Exception {
        mockMvc.perform(post("/api/model-connections")
                        .header("Origin", "https://untrusted.example")
                        .contentType("application/json").content("{}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void incorrectTokenReturns403() throws Exception {
        mockMvc.perform(get("/api/model-connections/1/runtime")
                        .header("X-SmartOps-Internal-Token", "wrong"))
                .andExpect(status().isForbidden());
    }

    @Test
    void validTokenReturnsOnlyNonSecretRuntimeMetadata() throws Exception {
        when(service.getRuntimeConfiguration(7L, 1L)).thenReturn(
                RuntimeModelConnectionResponse.builder()
                        .provider("openai-compatible")
                        .baseUrl("https://model.example/v1")
                        .modelName("ops-model")
                        .enabled(true)
                        .timeoutSeconds(60)
                        .keyLast4("abcd")
                        .build()
        );

        mockMvc.perform(get("/api/model-connections/1/runtime")
                        .header("X-User-Id", "7")
                        .header("X-SmartOps-Internal-Token", "test-internal-token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.provider").value("openai-compatible"))
                .andExpect(jsonPath("$.baseUrl").value("https://model.example/v1"))
                .andExpect(jsonPath("$.modelName").value("ops-model"))
                .andExpect(jsonPath("$.enabled").value(true))
                .andExpect(jsonPath("$.timeoutSeconds").value(60))
                .andExpect(jsonPath("$.keyLast4").value("abcd"))
                .andExpect(jsonPath("$.apiKeyCiphertext").doesNotExist())
                .andExpect(jsonPath("$.apiKeyPlaintext").doesNotExist())
                .andExpect(jsonPath("$.decryptedKey").doesNotExist());
    }

    @Test
    void invokeRequiresTokenAndReturnsNoCredential() throws Exception {
        mockMvc.perform(post("/api/model-connections/1/invoke")
                        .contentType("application/json")
                        .content("{\"prompt\":\"status\"}"))
                .andExpect(status().isUnauthorized());

        when(service.invoke(any(), any(), any())).thenReturn(
                ModelInvocationResponse.builder()
                        .connectionId(1L)
                        .provider("openai-compatible")
                        .model("ops-model")
                        .content("healthy")
                        .usage(java.util.Map.of("total_tokens", 4))
                        .build()
        );

        mockMvc.perform(post("/api/model-connections/1/invoke")
                        .header("X-SmartOps-Internal-Token", "test-internal-token")
                        .contentType("application/json")
                        .content("{\"prompt\":\"status\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").value("healthy"))
                .andExpect(jsonPath("$.apiKey").doesNotExist())
                .andExpect(jsonPath("$.apiKeyCiphertext").doesNotExist());
    }

    @Test
    void authenticatedUserCanCreateConnectionWithoutInternalToken() throws Exception {
        when(service.create(any(), any())).thenReturn(
                ModelConnectionResponse.builder()
                        .id(2L)
                        .userId(1L)
                        .name("local")
                        .provider("openai-compatible")
                        .baseUrl("https://model.example/v1")
                        .modelName("ops-model")
                        .apiKeyMasked("****abcd")
                        .enabled(true)
                        .timeoutSeconds(60)
                        .build()
        );

        mockMvc.perform(post("/api/model-connections")
                        .session(authenticatedSession()).header("X-CSRF-TOKEN", "test-csrf")
                        .contentType("application/json")
                        .content("{\"name\":\"local\",\"provider\":\"openai-compatible\","
                                + "\"baseUrl\":\"https://model.example/v1\",\"modelName\":\"ops-model\","
                                + "\"apiKey\":\"secret\",\"enabled\":true,\"timeoutSeconds\":60}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(2));
    }
}
