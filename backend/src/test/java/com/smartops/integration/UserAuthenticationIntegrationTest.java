package com.smartops.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.service.ModelConnectionService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@org.springframework.test.context.TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:smartops_auth_security;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
class UserAuthenticationIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    @MockBean ModelConnectionService models;
    private MockHttpSession session;
    private String csrf;

    @BeforeEach
    void prepare() {
        jdbc.execute("CREATE TABLE IF NOT EXISTS app_user (id BIGINT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(64) NOT NULL UNIQUE, password_hash VARCHAR(100) NOT NULL, role VARCHAR(16) NOT NULL, enabled BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        jdbc.update("DELETE FROM app_user");
        String hash = new BCryptPasswordEncoder().encode("AuditSecurePassword42!");
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(11,'audit-admin',?,'admin'),(22,'audit-operator',?,'operator')", hash, hash);
        // SEC-07：管理能力来自治理档案；SQL 种子的管理员按迁移回填语义显式建档。
        com.smartops.support.TestPlatformProfiles.grantRoot(jdbc, 11L);
    }

    private void token() throws Exception {
        var request = get("/api/auth/session");
        if (session != null) request.session(session);
        var result = mvc.perform(request).andExpect(status().isOk()).andReturn();
        session = (MockHttpSession) result.getRequest().getSession(false);
        csrf = json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText();
    }

    private void login(String username) throws Exception {
        token();
        mvc.perform(post("/api/auth/login").session(session).header("X-CSRF-TOKEN", csrf)
                .contentType("application/json").content("{\"username\":\"" + username + "\",\"password\":\"AuditSecurePassword42!\",\"role\":\"admin\",\"portal\":\"" + (username.equals("audit-admin") ? "admin" : "user") + "\"}"))
                .andExpect(status().isOk());
        token();
    }

    @Test void anonymousBusinessAccessIsDenied() throws Exception {
        mvc.perform(get("/api/operations/sessions")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/model-connections")).andExpect(status().isUnauthorized());
    }

    @Test void loginRequiresCsrfAndRejectsWrongPassword() throws Exception {
        mvc.perform(post("/api/auth/login").contentType("application/json").content("{}"))
                .andExpect(status().isForbidden());
        token();
        mvc.perform(post("/api/auth/login").session(session).header("X-CSRF-TOKEN", csrf)
                .contentType("application/json").content("{\"username\":\"audit-admin\",\"password\":\"incorrect\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test void serverSessionDeterminesRoleAndUserIdentity() throws Exception {
        login("audit-operator");
        mvc.perform(get("/api/auth/session").session(session))
                .andExpect(jsonPath("$.data.user.id").value(22))
                .andExpect(jsonPath("$.data.user.role").value("operator"));
        mvc.perform(get("/api/model-connections").session(session).header("X-User-Id", "11"))
                .andExpect(status().isOk());
        verify(models).list(22L);
        mvc.perform(get("/api/admin/users").session(session)).andExpect(status().isForbidden());
    }

    @Test void userChatNeedsUserSessionAndCsrfButNotAnInternalToken() throws Exception {
        login("audit-operator");
        when(models.invoke(eq(22L), eq(5L), any())).thenReturn(ModelInvocationResponse.builder().content("mock answer").build());
        mvc.perform(post("/api/chat/connections/5/invoke").session(session).contentType("application/json").content("{\"prompt\":\"hello\"}"))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/chat/connections/5/invoke").session(session).header("X-CSRF-TOKEN", csrf).header("X-User-Id", "11")
                .contentType("application/json").content("{\"prompt\":\"hello\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.content").value("mock answer"));
        verify(models).invoke(eq(22L), eq(5L), any());
        mvc.perform(get("/api/model-connections/5/runtime").session(session)).andExpect(status().isUnauthorized());
    }

    @Test void administratorCanCreateAnAccountAndLogoutRevokesAccess() throws Exception {
        login("audit-admin");
        mvc.perform(post("/api/admin/users").session(session).header("X-CSRF-TOKEN", csrf).header("X-Admin-Password", "AuditSecurePassword42!").contentType("application/json")
                .content("{\"username\":\"new-operator\",\"password\":\"NewSecurePassword42!\",\"role\":\"operator\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.passwordHash").doesNotExist());
        mvc.perform(post("/api/auth/logout").session(session).header("X-CSRF-TOKEN", csrf)).andExpect(status().isOk());
        mvc.perform(get("/api/admin/users")).andExpect(status().isUnauthorized());
    }
}
