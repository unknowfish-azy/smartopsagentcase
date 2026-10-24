package com.smartops.integration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.security.AccountSessionRegistry;
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
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:registration_security;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
class RegistrationSecurityIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @org.springframework.boot.test.mock.mockito.SpyBean JdbcTemplate jdbc;
    @Autowired AccountSessionRegistry sessions;
    @MockBean ModelConnectionService models;
    private static final String ADMIN_PASSWORD = "RegistrationAdminPassword42!";
    private static final String USER_PASSWORD = "UserPassword42!";
    private static final AtomicInteger SEQUENCE = new AtomicInteger();
    private String address;
    private String adminName;

    @BeforeEach void seed() {
        int sequence = SEQUENCE.incrementAndGet();
        address = "198.51.100." + sequence;
        adminName = "registration-admin-" + sequence;
        jdbc.queryForList("SELECT id FROM app_user", Long.class).forEach(sessions::revokeUser);
        jdbc.update("DELETE FROM account_security");
        jdbc.update("DELETE FROM app_user");
        jdbc.update("DELETE FROM security_audit_event");
        if (jdbc.queryForObject("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE LOWER(TABLE_NAME)='registration_policy'", Integer.class) > 0) {
            jdbc.update("UPDATE registration_policy SET enabled=TRUE WHERE id=1");
        }
        var encoder = new BCryptPasswordEncoder(4);
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(11,?,?,'admin'),(22,'existing-user',?,'operator')",
                adminName, encoder.encode(ADMIN_PASSWORD), encoder.encode(USER_PASSWORD));
    }

    private Client anonymous() throws Exception {
        var result = mvc.perform(get("/api/auth/session")).andExpect(status().isOk()).andReturn();
        return new Client((MockHttpSession) result.getRequest().getSession(false), json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }
    private ResultActions send(Client client, MockHttpServletRequestBuilder request, Object body) throws Exception {
        return mvc.perform(request.with(servlet -> { servlet.setRemoteAddr(address); return servlet; }).session(client.session())
                .header("X-CSRF-TOKEN", client.csrf()).contentType("application/json").content(json.writeValueAsString(body)));
    }
    private Client login(String username, String password, String portal) throws Exception {
        Client client = anonymous();
        send(client, post("/api/auth/login"), Map.of("username", username, "password", password, "portal", portal)).andExpect(status().isOk());
        var result = mvc.perform(get("/api/auth/session").session(client.session())).andReturn();
        return new Client(client.session(), json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }
    private Client admin() throws Exception { return login(adminName, ADMIN_PASSWORD, "admin"); }
    private Map<String, String> registration(String name, String password) {
        return Map.of("username", name, "password", password, "confirmPassword", password);
    }

    @Test void anonymousPolicyExplainsPasswordsAndRegistrationRequiresCsrf() throws Exception {
        mvc.perform(get("/api/auth/registration")).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.enabled").value(true)).andExpect(jsonPath("$.data.userPasswordMinLength").value(12))
                .andExpect(jsonPath("$.data.adminPasswordMinLength").value(16));
        mvc.perform(post("/api/auth/register").contentType("application/json").content(json.writeValueAsString(registration("csrf-user", USER_PASSWORD))))
                .andExpect(status().isForbidden());
    }

    @Test void registrationPersistsHashedOrdinaryAccountWithoutLoggingItIn() throws Exception {
        Client visitor = anonymous();
        var response = send(visitor, post("/api/auth/register"), registration("new-user", USER_PASSWORD)).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.role").value("operator")).andExpect(jsonPath("$.data.mustChangePassword").value(false)).andReturn();
        assertThat(response.getResponse().getContentAsString()).doesNotContain(USER_PASSWORD, "password_hash", "csrfToken");
        String hash = jdbc.queryForObject("SELECT password_hash FROM app_user WHERE username='new-user'", String.class);
        assertThat(hash).isNotEqualTo(USER_PASSWORD);
        assertThat(new BCryptPasswordEncoder().matches(USER_PASSWORD, hash)).isTrue();
        mvc.perform(get("/api/model-connections").session(visitor.session())).andExpect(status().isUnauthorized());
        visitor.session().invalidate();
        Client account = login("new-user", USER_PASSWORD, "user");
        mvc.perform(get("/api/model-connections").session(account.session())).andExpect(status().isOk());
        mvc.perform(get("/api/admin/users").session(account.session())).andExpect(status().isForbidden());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM security_audit_event WHERE action='REGISTER' AND outcome='SUCCESS'", Long.class)).isEqualTo(1);
    }

    @Test void forgedRoleAndPortalNeverGrantAdministrativeRegistration() throws Exception {
        send(anonymous(), post("/api/auth/register"), Map.of("username", "forged-user", "password", USER_PASSWORD, "confirmPassword", USER_PASSWORD, "role", "admin", "portal", "admin"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.role").value("operator"));
        send(anonymous(), post("/api/auth/login"), Map.of("username", "forged-user", "password", USER_PASSWORD, "portal", "admin"))
                .andExpect(status().isForbidden());
    }

    @Test void duplicateWeakMismatchedAndOversizedPasswordsDoNotCreateAccounts() throws Exception {
        send(anonymous(), post("/api/auth/register"), registration("existing-user", USER_PASSWORD)).andExpect(status().isConflict());
        send(anonymous(), post("/api/auth/register"), registration("weak-user", "1")).andExpect(status().isBadRequest());
        send(anonymous(), post("/api/auth/register"), Map.of("username", "mismatch-user", "password", USER_PASSWORD, "confirmPassword", "different"))
                .andExpect(status().isBadRequest());
        send(anonymous(), post("/api/auth/register"), registration("unicode-user", "密".repeat(25))).andExpect(status().isBadRequest());
        send(anonymous(), post("/api/auth/register"), registration("1", USER_PASSWORD)).andExpect(status().isBadRequest());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM app_user", Long.class)).isEqualTo(2);
    }

    @Test void registrationRateLimitCountsRejectedAttempts() throws Exception {
        Client visitor = anonymous();
        for (int attempt = 0; attempt < 5; attempt++) send(visitor, post("/api/auth/register"), registration("limited-user", "weak")).andExpect(status().isBadRequest());
        send(visitor, post("/api/auth/register"), registration("limited-user", USER_PASSWORD)).andExpect(status().isTooManyRequests());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM app_user", Long.class)).isEqualTo(2);
    }

    @Test void registrationSwitchPersistsAndIsEnforcedOnTheServer() throws Exception {
        Client manager = admin();
        send(manager, put("/api/admin/registration").header("X-Admin-Password", ADMIN_PASSWORD), Map.of("enabled", false))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.enabled").value(false));
        assertThat(jdbc.queryForObject("SELECT enabled FROM registration_policy WHERE id=1", Boolean.class)).isFalse();
        mvc.perform(get("/api/auth/registration")).andExpect(jsonPath("$.data.enabled").value(false));
        send(anonymous(), post("/api/auth/register"), registration("closed-user", USER_PASSWORD)).andExpect(status().isForbidden());
        send(manager, put("/api/admin/registration").header("X-Admin-Password", ADMIN_PASSWORD), Map.of("enabled", true)).andExpect(status().isOk());
        send(anonymous(), post("/api/auth/register"), registration("reopened-user", USER_PASSWORD)).andExpect(status().isOk());
    }

    @Test void ordinaryAndUserPortalAccountsCannotChangeRegistrationPolicy() throws Exception {
        Client account = login("existing-user", USER_PASSWORD, "user");
        send(account, put("/api/admin/registration").header("X-Admin-Password", USER_PASSWORD), Map.of("enabled", false)).andExpect(status().isForbidden());
        send(anonymous(), post("/api/auth/login"), Map.of("username", adminName, "password", ADMIN_PASSWORD, "portal", "user")).andExpect(status().isForbidden());
        assertThat(jdbc.queryForObject("SELECT enabled FROM registration_policy WHERE id=1", Boolean.class)).isTrue();
    }

    @Test void administratorMutationsRequireCurrentPasswordWithoutEndingSession() throws Exception {
        Client manager = admin();
        send(manager, put("/api/admin/users/22"), Map.of("role", "operator", "enabled", false)).andExpect(status().isForbidden());
        send(manager, put("/api/admin/users/22").header("X-Admin-Password", "wrong-secondary-secret"), Map.of("role", "operator", "enabled", false)).andExpect(status().isForbidden());
        assertThat(jdbc.queryForObject("SELECT enabled FROM app_user WHERE id=22", Boolean.class)).isTrue();
        mvc.perform(get("/api/admin/users").session(manager.session())).andExpect(status().isOk());
        send(manager, put("/api/admin/users/22").header("X-Admin-Password", ADMIN_PASSWORD), Map.of("role", "operator", "enabled", false)).andExpect(status().isOk());
        var events = mvc.perform(get("/api/admin/audit").session(manager.session()).param("action", "ADMIN_VERIFY")).andExpect(status().isOk()).andReturn();
        assertThat(events.getResponse().getContentAsString()).doesNotContain(ADMIN_PASSWORD, "wrong-secondary-secret");
    }

    @Test void missingSecondaryPasswordProtectsCreateResetRevokeAndPolicy() throws Exception {
        Client manager = admin();
        send(manager, post("/api/admin/users"), Map.of("username", "protected-user", "password", USER_PASSWORD, "role", "operator")).andExpect(status().isForbidden());
        send(manager, post("/api/admin/users/22/reset-password"), Map.of("password", USER_PASSWORD + "changed")).andExpect(status().isForbidden());
        send(manager, delete("/api/admin/sessions/not-a-session"), Map.of()).andExpect(status().isForbidden());
        send(manager, put("/api/admin/registration"), Map.of("enabled", false)).andExpect(status().isForbidden());
    }

    @Test void administratorLoginLimitCannotBeClearedThroughTheUserPortal() throws Exception {
        jdbc.update("UPDATE app_user SET id=3333 WHERE id=11");
        Client visitor = anonymous();
        for (int attempt = 0; attempt < 5; attempt++) send(visitor, post("/api/auth/login"), Map.of("username", adminName, "password", "wrong", "portal", "admin")).andExpect(status().isUnauthorized());
        send(anonymous(), post("/api/auth/login"), Map.of("username", adminName, "password", ADMIN_PASSWORD, "portal", "user")).andExpect(status().isTooManyRequests());
        send(visitor, post("/api/auth/login"), Map.of("username", adminName, "password", ADMIN_PASSWORD, "portal", "admin")).andExpect(status().isTooManyRequests());
    }

    @Test void encodedAdministrativeRoutesCannotBypassPasswordConfirmation() throws Exception {
        Client manager = admin();
        send(manager, put(java.net.URI.create("/api/%61dmin/registration")), Map.of("enabled", false)).andExpect(status().isForbidden());
        send(manager, put(java.net.URI.create("/api/%61dmin/registration")).header("X-Admin-Password", "wrong"), Map.of("enabled", false))
                .andExpect(status().isForbidden());
        assertThat(jdbc.queryForObject("SELECT enabled FROM registration_policy WHERE id=1", Boolean.class)).isTrue();
    }

    @Test void blockedRegistrationSourceCannotExhaustTheGlobalBudget() throws Exception {
        Client visitor = anonymous();
        for (int attempt = 0; attempt < 105; attempt++) {
            send(visitor, post("/api/auth/register"), registration("abusive-user", "weak"))
                    .andExpect(attempt < 5 ? status().isBadRequest() : status().isTooManyRequests());
        }
        address = "203.0.113.250";
        send(anonymous(), post("/api/auth/register"), registration("other-source", USER_PASSWORD)).andExpect(status().isOk());
    }

    @SuppressWarnings("unchecked")
    @Test void databaseEquivalentNamesShareTheSameAccountLimit() throws Exception {
        jdbc.update("UPDATE app_user SET id=4444 WHERE id=11");
        String equivalentName = adminName + " ";
        org.mockito.Mockito.doAnswer(invocation -> jdbc.query(invocation.getArgument(0, String.class),
                invocation.getArgument(1, org.springframework.jdbc.core.RowMapper.class), adminName))
                .when(jdbc).query(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.any(org.springframework.jdbc.core.RowMapper.class), org.mockito.ArgumentMatchers.eq(equivalentName));
        Client visitor = anonymous();
        for (int attempt = 0; attempt < 5; attempt++) {
            send(visitor, post("/api/auth/login"), Map.of("username", equivalentName, "password", "wrong", "portal", "admin"))
                    .andExpect(status().isUnauthorized());
        }
        address = "203.0.113.251";
        send(anonymous(), post("/api/auth/login"), Map.of("username", adminName, "password", ADMIN_PASSWORD, "portal", "admin"))
                .andExpect(status().isTooManyRequests());
    }

    @Test void secondaryPasswordFailuresAreRateLimited() throws Exception {
        jdbc.update("UPDATE app_user SET id=1111 WHERE id=11");
        Client manager = admin();
        for (int attempt = 0; attempt < 5; attempt++) send(manager, put("/api/admin/registration").header("X-Admin-Password", "wrong"), Map.of("enabled", false)).andExpect(status().isForbidden());
        send(manager, put("/api/admin/registration").header("X-Admin-Password", ADMIN_PASSWORD), Map.of("enabled", false)).andExpect(status().isTooManyRequests());
    }

    @Test void administratorSessionsHaveShorterIdleLifetime() throws Exception {
        assertThat(admin().session().getMaxInactiveInterval()).isEqualTo(600);
        assertThat(login("existing-user", USER_PASSWORD, "user").session().getMaxInactiveInterval()).isEqualTo(1800);
    }

    @Test void passwordChangeCannotBypassTheAdministratorConfirmationLimit() throws Exception {
        jdbc.update("UPDATE app_user SET id=2222 WHERE id=11");
        Client manager = admin();
        send(anonymous(), post("/api/auth/login"), Map.of("username", adminName, "password", ADMIN_PASSWORD, "portal", "user")).andExpect(status().isForbidden());
        for (int attempt = 0; attempt < 5; attempt++) {
            send(manager, put("/api/admin/registration").header("X-Admin-Password", "wrong"), Map.of("enabled", false))
                    .andExpect(status().isForbidden());
        }
        send(manager, put("/api/admin/registration").header("X-Admin-Password", ADMIN_PASSWORD), Map.of("enabled", false))
                .andExpect(status().isTooManyRequests());
    }

    @Test void csrfIsCheckedBeforeAdministrativePasswordVerification() throws Exception {
        Client manager = admin();
        mvc.perform(put("/api/admin/registration").session(manager.session()).header("X-Admin-Password", ADMIN_PASSWORD)
                .contentType("application/json").content("{\"enabled\":false}"))
                .andExpect(status().isForbidden());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM security_audit_event WHERE action='ADMIN_VERIFY'", Long.class)).isZero();
    }

    @Test void concurrentRegistrationsCannotCreateDuplicateAccounts() throws Exception {
        Client first = anonymous();
        Client second = anonymous();
        var executor = java.util.concurrent.Executors.newFixedThreadPool(2);
        var start = new java.util.concurrent.CountDownLatch(1);
        try {
            var firstResult = executor.submit(() -> { start.await(); return send(first, post("/api/auth/register"), registration("racing-user", USER_PASSWORD)).andReturn().getResponse().getStatus(); });
            var secondResult = executor.submit(() -> { start.await(); return send(second, post("/api/auth/register"), registration("racing-user", USER_PASSWORD)).andReturn().getResponse().getStatus(); });
            start.countDown();
            assertThat(java.util.List.of(firstResult.get(15, java.util.concurrent.TimeUnit.SECONDS), secondResult.get(15, java.util.concurrent.TimeUnit.SECONDS)))
                    .containsExactlyInAnyOrder(200, 409);
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM app_user WHERE username='racing-user'", Long.class)).isEqualTo(1);
        } finally { executor.shutdownNow(); }
    }

    @Test void strongerAdministratorPasswordAppliesToCreateResetAndOwnChange() throws Exception {
        Client manager = admin();
        send(manager, post("/api/admin/users").header("X-Admin-Password", ADMIN_PASSWORD), Map.of("username", "short-admin", "password", USER_PASSWORD, "role", "admin")).andExpect(status().isBadRequest());
        send(manager, post("/api/admin/users/11/reset-password").header("X-Admin-Password", ADMIN_PASSWORD), Map.of("password", USER_PASSWORD)).andExpect(status().isBadRequest());
        send(manager, post("/api/auth/password"), Map.of("currentPassword", ADMIN_PASSWORD, "newPassword", USER_PASSWORD)).andExpect(status().isBadRequest());
        send(manager, post("/api/admin/users").header("X-Admin-Password", ADMIN_PASSWORD), Map.of("username", "strong-admin", "password", ADMIN_PASSWORD, "role", "admin"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.mustChangePassword").value(true));
    }

    @Test void promotionRequiresPasswordChangeBeforeManagementAccess() throws Exception {
        Client manager = admin();
        send(manager, put("/api/admin/users/22").header("X-Admin-Password", ADMIN_PASSWORD), Map.of("role", "admin", "enabled", true))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.mustChangePassword").value(true));
        Client promoted = login("existing-user", USER_PASSWORD, "admin");
        mvc.perform(get("/api/admin/users").session(promoted.session())).andExpect(status().isForbidden());
        send(promoted, post("/api/auth/password"), Map.of("currentPassword", USER_PASSWORD, "newPassword", "LongEnoughAdminPassword43!"))
                .andExpect(status().isOk());
        Client updated = login("existing-user", "LongEnoughAdminPassword43!", "admin");
        mvc.perform(get("/api/admin/users").session(updated.session())).andExpect(status().isOk());
    }

    @Test void existingAdministratorPasswordIsNotSilentlyReplaced() throws Exception {
        String legacyPassword = "LegacyOnly12!";
        String hash = new BCryptPasswordEncoder(4).encode(legacyPassword);
        jdbc.update("UPDATE app_user SET password_hash=? WHERE id=11", hash);
        login(adminName, legacyPassword, "admin");
        assertThat(jdbc.queryForObject("SELECT password_hash FROM app_user WHERE id=11", String.class)).isEqualTo(hash);
    }

    private record Client(MockHttpSession session, String csrf) {}
}
