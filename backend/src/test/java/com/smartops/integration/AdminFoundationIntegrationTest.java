package com.smartops.integration;

import com.fasterxml.jackson.databind.JsonNode;
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
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.util.Map;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:admin_foundation;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
class AdminFoundationIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    @Autowired com.smartops.security.AccountSessionRegistry sessions;
    @Autowired com.smartops.security.UserAccountService accounts;
    @org.springframework.boot.test.mock.mockito.SpyBean com.smartops.security.SecurityAuditService audit;
    @org.springframework.boot.test.mock.mockito.MockBean com.smartops.service.ModelConnectionService models;
    private static final String PASSWORD = "AdminFoundationPassword42!";

    @BeforeEach void seed() {
        jdbc.queryForList("SELECT id FROM app_user", Long.class).forEach(sessions::revokeUser);
        jdbc.update("DELETE FROM app_user");
        for (String table : List.of("account_security", "security_audit_event")) {
            if (jdbc.queryForObject("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE LOWER(TABLE_NAME)=?", Integer.class, table) > 0) jdbc.update("DELETE FROM " + table);
        }
        String hash = new BCryptPasswordEncoder().encode(PASSWORD);
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(11,'foundation-admin',?,'admin'),(22,'foundation-user',?,'operator')", hash, hash);
    }

    private Client anonymous() throws Exception {
        var result = mvc.perform(get("/api/auth/session")).andExpect(status().isOk()).andReturn();
        return new Client((MockHttpSession) result.getRequest().getSession(false), json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }

    private Client login(String name, String password, String portal) throws Exception {
        Client client = anonymous();
        send(client, post("/api/auth/login"), Map.of("username", name, "password", password, "portal", portal)).andExpect(status().isOk());
        var result = mvc.perform(get("/api/auth/session").session(client.session())).andExpect(status().isOk()).andReturn();
        return new Client((MockHttpSession) result.getRequest().getSession(false), json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }

    private Client admin() throws Exception { return login("foundation-admin", PASSWORD, "admin"); }
    private ResultActions send(Client client, MockHttpServletRequestBuilder request, Object body) throws Exception {
        return mvc.perform(request.session(client.session()).header("X-CSRF-TOKEN", client.csrf()).header("X-Admin-Password", PASSWORD).contentType("application/json").content(json.writeValueAsString(body)));
    }
    private JsonNode data(ResultActions result) throws Exception {
        return json.readTree(result.andReturn().getResponse().getContentAsString()).path("data");
    }

    @Test void portalSelectionDoesNotGrantManagementAuthority() throws Exception {
        send(anonymous(), post("/api/auth/login"), Map.of("username", "foundation-user", "password", PASSWORD, "portal", "admin", "role", "admin")).andExpect(status().isForbidden());
        send(anonymous(), post("/api/auth/login"), Map.of("username", "foundation-admin", "password", PASSWORD, "portal", "user")).andExpect(status().isForbidden());
        Client manager = admin();
        mvc.perform(get("/api/admin/overview").session(manager.session())).andExpect(status().isOk()).andExpect(jsonPath("$.data.usersTotal").value(2));
    }

    @Test void revokedPlatformAdminDoesNotRegainCapabilities() {
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(33,'foundation-deputy',?,'admin')", new BCryptPasswordEncoder().encode(PASSWORD));
        var root = new com.smartops.security.SessionUser(11L, "foundation-admin", "admin", "admin", false, 0);
        var deputy = new com.smartops.security.SessionUser(33L, "foundation-deputy", "admin", "admin", false, 0);

        accounts.appointPlatformAdmin(root, 33L, "deputy", List.of("admin.users"));
        assertThat(accounts.hasPlatformCapability(deputy, "admin.users")).isTrue();

        accounts.revokePlatformAdmin(root, 33L);
        // 撤销保留档案并写入 revoked_at：不得因为缺少能力行被当成“历史管理员”重新放行。
        assertThat(accounts.hasPlatformCapability(deputy, "admin.users")).isFalse();
        assertThat(accounts.hasPlatformCapability(deputy, "admin.audit")).isFalse();
        assertThat(jdbc.queryForObject("SELECT revoked_at FROM platform_admin_profile WHERE user_id=33", java.sql.Timestamp.class)).isNotNull();
        // 历史存量管理员（无档案）语义保持不变。
        assertThat(accounts.hasPlatformCapability(root, "admin.users")).isTrue();
    }

    private com.smartops.security.SessionUser revokedManager() {
        jdbc.update("UPDATE app_user SET role='admin' WHERE id=22");
        var snapshot = new com.smartops.security.SessionUser(22L, "foundation-user", "admin", "admin", false, 0);
        jdbc.update("UPDATE app_user SET role='operator' WHERE id=22");
        return snapshot;
    }

    @Test void actorRevokedAfterRequestAuthorizationCannotResetPasswords() {
        var actor = revokedManager();
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> accounts.resetPassword(11L, "StaleActorPassword42!", actor))
                .isInstanceOfSatisfying(com.smartops.exception.BusinessException.class, error -> assertThat(error.getCode()).isEqualTo(401));
    }

    @Test void actorRevokedAfterRequestAuthorizationCannotChangeAccounts() {
        var actor = revokedManager();
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> accounts.update(22L, "admin", true, null, null, null, actor))
                .isInstanceOfSatisfying(com.smartops.exception.BusinessException.class, error -> assertThat(error.getCode()).isEqualTo(401));
    }

    @Test void actorRevokedAfterRequestAuthorizationCannotCreateAccounts() {
        var actor = revokedManager();
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> accounts.create("stale-created", PASSWORD, "admin", null, null, null, actor))
                .isInstanceOfSatisfying(com.smartops.exception.BusinessException.class, error -> assertThat(error.getCode()).isEqualTo(401));
    }

    @Test void failedRevocationAuditLeavesTheSessionUsable() throws Exception {
        Client manager = admin();
        Client target = login("foundation-user", PASSWORD, "user");
        JsonNode items = data(mvc.perform(get("/api/auth/sessions").session(target.session()))).path("items");
        String id = items.get(0).path("id").asText();
        org.mockito.Mockito.doThrow(new IllegalStateException("test audit unavailable")).when(audit).record(org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.eq("REVOKE_SESSION"), org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.eq("SUCCESS"));
        send(manager, delete("/api/admin/sessions/" + id), Map.of()).andExpect(status().isInternalServerError());
        mvc.perform(get("/api/model-connections").session(target.session())).andExpect(status().isOk());
    }

    @Test void missingPortalDefaultsToUserAndUnknownPortalIsRejected() throws Exception {
        Client client = anonymous();
        send(client, post("/api/auth/login"), Map.of("username", "foundation-admin", "password", PASSWORD)).andExpect(status().isForbidden());
        send(anonymous(), post("/api/auth/login"), Map.of("username", "foundation-admin", "password", PASSWORD, "portal", "root")).andExpect(status().isBadRequest());
    }

    @Test void accountListIsPaginatedSearchableAndSecretFree() throws Exception {
        Client manager = admin();
        var result = mvc.perform(get("/api/admin/users").param("q", "foundation-user").param("pageSize", "1").session(manager.session()))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(1)).andExpect(jsonPath("$.data.items[0].enabled").value(true)).andReturn();
        assertThat(result.getResponse().getContentAsString()).doesNotContain("password_hash", "passwordHash", PASSWORD);
        mvc.perform(get("/api/admin/users").param("page", "0").session(manager.session())).andExpect(status().isBadRequest());
        mvc.perform(get("/api/admin/users").param("q", "%").session(manager.session())).andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(0));
    }

    @Test void disabledAccountLosesOldSessionsAndCanBeRestored() throws Exception {
        Client target = login("foundation-user", PASSWORD, "user");
        Client manager = admin();
        send(manager, put("/api/admin/users/22"), Map.of("role", "operator", "enabled", false)).andExpect(status().isOk());
        mvc.perform(get("/api/model-connections").session(target.session())).andExpect(status().isUnauthorized());
        send(anonymous(), post("/api/auth/login"), Map.of("username", "foundation-user", "password", PASSWORD, "portal", "user")).andExpect(status().isUnauthorized());
        send(manager, put("/api/admin/users/22"), Map.of("role", "operator", "enabled", true)).andExpect(status().isOk());
        login("foundation-user", PASSWORD, "user");
    }

    @Test void roleChangeRevokesAllExistingAuthority() throws Exception {
        jdbc.update("UPDATE app_user SET role='admin' WHERE id=22");
        Client target = login("foundation-user", PASSWORD, "admin");
        Client manager = admin();
        send(manager, put("/api/admin/users/22"), Map.of("role", "operator", "enabled", true)).andExpect(status().isOk());
        mvc.perform(get("/api/admin/users").session(target.session())).andExpect(status().isUnauthorized());
    }

    @Test void passwordResetRequiresChangeBeforeAnyBusinessRequest() throws Exception {
        Client target = login("foundation-user", PASSWORD, "user");
        Client manager = admin();
        send(manager, post("/api/admin/users/22/reset-password"), Map.of("password", "TemporaryPassword42!")).andExpect(status().isOk());
        mvc.perform(get("/api/model-connections").session(target.session())).andExpect(status().isUnauthorized());
        Client reset = login("foundation-user", "TemporaryPassword42!", "user");
        mvc.perform(get("/api/auth/session").session(reset.session())).andExpect(jsonPath("$.data.user.mustChangePassword").value(true));
        mvc.perform(get("/api/model-connections").session(reset.session())).andExpect(status().isForbidden());
        send(reset, post("/api/auth/password"), Map.of("currentPassword", "wrong-password", "newPassword", "PermanentPassword42!")).andExpect(status().isBadRequest());
        send(reset, post("/api/auth/password"), Map.of("currentPassword", "TemporaryPassword42!", "newPassword", "PermanentPassword42!")).andExpect(status().isOk());
        mvc.perform(get("/api/model-connections").session(reset.session())).andExpect(status().isUnauthorized());
        Client changed = login("foundation-user", "PermanentPassword42!", "user");
        mvc.perform(get("/api/model-connections").session(changed.session())).andExpect(status().isOk());
    }

    @Test void createdAccountsMustChangePasswordAndWeakPasswordsAreRejected() throws Exception {
        Client manager = admin();
        send(manager, post("/api/admin/users"), Map.of("username", "created-user", "password", PASSWORD, "role", "operator"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.mustChangePassword").value(true));
        Client created = login("created-user", PASSWORD, "user");
        mvc.perform(get("/api/admin/users").session(created.session())).andExpect(status().isForbidden());
        send(manager, post("/api/admin/users/22/reset-password"), Map.of("password", "weak")).andExpect(status().isBadRequest());
    }

    @Test void lastAdministratorCannotBeDisabledOrDemoted() throws Exception {
        Client manager = admin();
        send(manager, put("/api/admin/users/11"), Map.of("role", "admin", "enabled", false)).andExpect(status().isConflict());
        send(manager, put("/api/admin/users/11"), Map.of("role", "operator", "enabled", true)).andExpect(status().isConflict());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM app_user WHERE role='admin' AND enabled=TRUE", Long.class)).isEqualTo(1);
    }

    @Test void concurrentDemotionsStillLeaveAnEnabledAdministrator() throws Exception {
        jdbc.update("UPDATE app_user SET role='admin' WHERE id=22");
        Client first = admin();
        Client second = login("foundation-user", PASSWORD, "admin");
        var executor = Executors.newFixedThreadPool(2);
        var start = new CountDownLatch(1);
        try {
            var firstResult = executor.submit(() -> { start.await(); return send(first, put("/api/admin/users/11"), Map.of("role", "operator", "enabled", true)).andReturn().getResponse().getStatus(); });
            var secondResult = executor.submit(() -> { start.await(); return send(second, put("/api/admin/users/22"), Map.of("role", "operator", "enabled", true)).andReturn().getResponse().getStatus(); });
            start.countDown();
            assertThat(List.of(firstResult.get(15, TimeUnit.SECONDS), secondResult.get(15, TimeUnit.SECONDS))).containsExactlyInAnyOrder(200, 409);
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM app_user WHERE role='admin' AND enabled=TRUE", Long.class)).isEqualTo(1);
        } finally { executor.shutdownNow(); }
    }

    @Test void sessionManagementUsesOpaqueIdsAndRevokesOnlyTheTarget() throws Exception {
        Client manager = admin();
        Client target = login("foundation-user", PASSWORD, "user");
        JsonNode items = data(mvc.perform(get("/api/admin/sessions").session(manager.session())).andExpect(status().isOk())).path("items");
        assertThat(items.toString()).doesNotContain("sessionId", "csrfToken", "JSESSIONID", manager.csrf());
        for (JsonNode item : items) assertThat(item.path("id").asText()).isNotIn(target.session().getId(), manager.session().getId());
        String targetId = "";
        for (JsonNode item : items) if (item.path("userId").asLong() == 22L) targetId = item.path("id").asText();
        assertThat(targetId).isNotBlank();
        send(manager, delete("/api/admin/sessions/" + targetId), Map.of()).andExpect(status().isOk());
        mvc.perform(get("/api/model-connections").session(target.session())).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/admin/users").session(manager.session())).andExpect(status().isOk());
    }

    @Test void userCannotRevokeAnotherUsersSessionAndAuditContainsNoSecrets() throws Exception {
        Client manager = admin();
        Client target = login("foundation-user", PASSWORD, "user");
        JsonNode items = data(mvc.perform(get("/api/auth/sessions").session(manager.session()))).path("items");
        String ownId = items.get(0).path("id").asText();
        send(target, delete("/api/auth/sessions/" + ownId), Map.of()).andExpect(status().isNotFound());
        send(anonymous(), post("/api/auth/login"), Map.of("username", "foundation-user", "password", "wrong-audit-secret", "portal", "user")).andExpect(status().isUnauthorized());
        var result = mvc.perform(get("/api/admin/audit").param("action", "LOGIN").param("outcome", "FAILURE").param("q", "foundation-user").session(manager.session()))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(1)).andReturn();
        assertThat(result.getResponse().getContentAsString()).doesNotContain("wrong-audit-secret", PASSWORD, manager.csrf(), "sessionId", "JSESSIONID");
        mvc.perform(get("/api/admin/audit").session(target.session())).andExpect(status().isForbidden());
    }

    private record Client(MockHttpSession session, String csrf) {}
}
