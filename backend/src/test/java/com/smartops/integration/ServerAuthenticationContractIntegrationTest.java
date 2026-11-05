package com.smartops.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Real filters, login, controller, service, mapper and isolated H2; no HTTP/service doubles. */
@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:server_auth_contract;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ServerAuthenticationContractIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    private MockHttpSession session;
    private String csrf;
    private static final String PASSWORD = "ServerContractPassword42!";
    private static final String BODY = "{\"name\":\"auth-contract-server\",\"host\":\"127.0.0.1\",\"port\":22}";

    @BeforeEach void seed() {
        jdbc.update("DELETE FROM server WHERE name='auth-contract-server'");
        jdbc.update("DELETE FROM app_user WHERE username IN ('contract-admin','contract-operator')");
        String hash = new BCryptPasswordEncoder().encode(PASSWORD);
        jdbc.update("INSERT INTO app_user(username,password_hash,role) VALUES('contract-admin',?,'admin'),('contract-operator',?,'operator')", hash, hash);
    }
    private void token() throws Exception {
        var request = get("/api/auth/session");
        if (session != null) request.session(session);
        var result = mvc.perform(request).andExpect(status().isOk()).andReturn();
        session = (MockHttpSession) result.getRequest().getSession(false);
        csrf = json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText();
        assertFalse(csrf.isBlank());
    }
    private void login(String role) throws Exception {
        token();
        mvc.perform(post("/api/auth/login").session(session).header("X-CSRF-TOKEN", csrf)
            .contentType("application/json").content(json.writeValueAsString(Map.of("username", "contract-" + role, "password", PASSWORD, "portal", role.equals("admin") ? "admin" : "user"))))
            .andExpect(status().isOk());
        token();
    }
    @Test void anonymousAndForgedSessionCannotReadOrWrite() throws Exception {
        mvc.perform(get("/api/servers")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/servers").cookie(new jakarta.servlet.http.Cookie("JSESSIONID", "forged"))).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/servers").contentType("application/json").content(BODY)).andExpect(status().isForbidden());
        token();
        mvc.perform(post("/api/servers").session(session).header("X-CSRF-TOKEN", csrf).contentType("application/json").content(BODY)).andExpect(status().isUnauthorized());
    }
    @Test void operatorCanReadSeededMonitoringButCannotCreateEvenWithCsrf() throws Exception {
        login("operator");
        for (int size : new int[]{10, 20, 50})
            mvc.perform(get("/api/servers").param("page", "1").param("size", String.valueOf(size)).session(session)).andExpect(status().isOk()).andExpect(jsonPath("$.data[0].id").isNumber());
        mvc.perform(get("/api/servers/999999999").session(session)).andExpect(status().isBadRequest());
        for (int id : new int[]{0, -1, 999999999})
            mvc.perform(get("/api/servers/" + id + "/metrics/latest").session(session)).andExpect(status().isBadRequest());
        mvc.perform(get("/api/servers/1/metrics/latest").session(session)).andExpect(status().isOk()).andExpect(jsonPath("$.data.serverId").value(1));
        mvc.perform(get("/api/servers/1/metrics").session(session)).andExpect(status().isOk());
        mvc.perform(post("/api/servers").session(session).header("X-CSRF-TOKEN", csrf).contentType("application/json").content(BODY)).andExpect(status().isForbidden());
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM server WHERE name='auth-contract-server'", Integer.class));
    }
    @Test void authenticatedAdminCreatesQueriesAndCleansUpOnlyWithCsrf() throws Exception {
        login("admin");
        mvc.perform(post("/api/servers").session(session).contentType("application/json").content(BODY)).andExpect(status().isForbidden());
        mvc.perform(post("/api/servers").session(session).header("X-CSRF-TOKEN", "wrong").contentType("application/json").content(BODY)).andExpect(status().isForbidden());
        var result = mvc.perform(post("/api/servers").session(session).header("X-CSRF-TOKEN", csrf).contentType("application/json").content(BODY))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.name").value("auth-contract-server")).andReturn();
        long id = json.readTree(result.getResponse().getContentAsString()).path("data").path("id").asLong();
        assertTrue(id > 0);
        try {
            mvc.perform(get("/api/servers/" + id).session(session)).andExpect(status().isOk()).andExpect(jsonPath("$.data.id").value(id));
            mvc.perform(get("/api/servers").session(session)).andExpect(status().isOk()).andExpect(jsonPath("$.data[?(@.name == 'auth-contract-server')]").isNotEmpty());
            for (String invalid : new String[]{"{}", "{\"name\":\"invalid\",\"host\":\"127.0.0.1\",\"port\":-1}"})
                mvc.perform(post("/api/servers").session(session).header("X-CSRF-TOKEN", csrf).contentType("application/json").content(invalid)).andExpect(status().isBadRequest());
        } finally {
            mvc.perform(delete("/api/servers/" + id).session(session).header("X-CSRF-TOKEN", csrf)).andExpect(status().isOk());
        }
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM server WHERE id=?", Integer.class, id));
        mvc.perform(post("/api/auth/logout").session(session).header("X-CSRF-TOKEN", csrf)).andExpect(status().isOk());
        mvc.perform(get("/api/servers")).andExpect(status().isUnauthorized());
    }
}
