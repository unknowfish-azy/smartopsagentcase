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
        // SEC-07：治理档案是能力的唯一来源；SQL 种子的管理员按迁移回填语义显式建档。
        com.smartops.support.TestPlatformProfiles.grantRoot(jdbc, 11L);
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
        // SEC-07：SQL 直提的管理员没有治理档案，按最小只读会被 403 拒绝。
        // 这里显式任命为 deputy 并授予 admin.users，保持“两个有权限的管理员互降”的竞态意图。
        var promoter = new com.smartops.security.SessionUser(11L, "foundation-admin", "admin", "admin", false, 0);
        accounts.appointPlatformAdmin(promoter, 22L, "deputy", List.of("admin.users"));
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

    @Test void deputyWithoutConfigCapabilityCannotWriteSystemConfiguration() throws Exception {
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(44,'foundation-config-less',?,'admin')", new BCryptPasswordEncoder().encode(PASSWORD));
        var root = new com.smartops.security.SessionUser(11L, "foundation-admin", "admin", "admin", false, 0);
        accounts.appointPlatformAdmin(root, 44L, "specialist", List.of("admin.users"));
        Client limited = login("foundation-config-less", PASSWORD, "admin");
        // 账号页需要读取组织选项：admin.users 可读配置元数据，但写配置必须 admin.config。
        mvc.perform(get("/api/admin/system/depts").session(limited.session())).andExpect(status().isOk());
        send(limited, post("/api/admin/system/posts"), Map.of("code", "ops", "name", "运维", "sort", 1, "remark", "")).andExpect(status().isForbidden());
        // 审计与登录日志需要 admin.audit，不在 admin.users 范围内。
        mvc.perform(get("/api/admin/audit").session(limited.session())).andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/system/login-logs").session(limited.session())).andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/users").session(limited.session())).andExpect(status().isOk());
    }

    @Test void revokedPlatformAdminLosesManagementReadsAfterRelogin() throws Exception {
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(55,'foundation-revoked',?,'admin')", new BCryptPasswordEncoder().encode(PASSWORD));
        var root = new com.smartops.security.SessionUser(11L, "foundation-admin", "admin", "admin", false, 0);
        accounts.appointPlatformAdmin(root, 55L, "deputy", List.of("admin.users"));
        accounts.revokePlatformAdmin(root, 55L);
        Client revoked = login("foundation-revoked", PASSWORD, "admin");
        mvc.perform(get("/api/admin/users").session(revoked.session())).andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/overview").session(revoked.session())).andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/users/22/context").session(revoked.session())).andExpect(status().isForbidden());
    }

    @Test void capabilityCatalogFollowsServerGrantRules() throws Exception {
        Client manager = admin();
        JsonNode catalog = data(mvc.perform(get("/api/admin/governance/capabilities").session(manager.session())).andExpect(status().isOk()));
        assertThat(catalog.path("level").asText()).isEqualTo("root");
        assertThat(catalog.path("manageableLevels").toString()).contains("deputy", "specialist");
        assertThat(catalog.path("items").size()).isEqualTo(9);
        for (JsonNode item : catalog.path("items")) {
            assertThat(item.path("grantable").asBoolean()).isTrue();
            assertThat(item.path("label").asText()).isNotBlank();
        }
        // 历史未建档管理员继续按最高管理员语义放行。
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(66,'foundation-deputy2',?,'admin')", new BCryptPasswordEncoder().encode(PASSWORD));
        accounts.appointPlatformAdmin(new com.smartops.security.SessionUser(11L, "foundation-admin", "admin", "admin", false, 0), 66L, "deputy", List.of("admin.users"));
        Client deputy = login("foundation-deputy2", PASSWORD, "admin");
        JsonNode deputyCatalog = data(mvc.perform(get("/api/admin/governance/capabilities").session(deputy.session())).andExpect(status().isOk()));
        assertThat(deputyCatalog.path("level").asText()).isEqualTo("deputy");
        assertThat(deputyCatalog.path("manageableLevels").toString()).contains("specialist").doesNotContain("deputy");
        for (JsonNode item : deputyCatalog.path("items")) {
            String capability = item.path("value").asText();
            // 副管理员可转授除 admin.security 之外的能力，转授范围以服务端规则为准。
            assertThat(item.path("grantable").asBoolean()).isEqualTo(!capability.equals("admin.security"));
        }
    }

    @Test void accountContextSummarisesGovernanceMetadataWithoutSecrets() throws Exception {
        Client manager = admin();
        var result = mvc.perform(get("/api/admin/users/22/context").session(manager.session())).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.account.username").value("foundation-user"))
                .andExpect(jsonPath("$.data.platformAdmin.profiled").value(false))
                .andExpect(jsonPath("$.data.protection.self").value(false))
                .andExpect(jsonPath("$.data.rbacRoles").isArray())
                .andExpect(jsonPath("$.data.sessions").isArray())
                .andExpect(jsonPath("$.data.recentAudit").isArray()).andReturn();
        assertThat(result.getResponse().getContentAsString()).doesNotContain("password_hash", "passwordHash", PASSWORD, manager.csrf(), "sessionId");
        mvc.perform(get("/api/admin/users/99991/context").session(manager.session())).andExpect(status().isNotFound());
    }

    @Test void auditSearchSupportsTargetAndDateRangeWithDetail() throws Exception {
        Client manager = admin();
        audit.record(new com.smartops.security.SessionUser(22L, "foundation-user", "operator", "user", false, 0), "TEAM_AGENT_RUN_APPROVE", "901", "SUCCESS", "approved: window 901");
        JsonNode page = data(mvc.perform(get("/api/admin/audit").param("target", "901").session(manager.session())).andExpect(status().isOk()));
        assertThat(page.path("total").asLong()).isEqualTo(1);
        long id = page.path("items").get(0).path("id").asLong();
        // 详情与列表同一作用域：依据必须单独可查，且不被拼进 outcome。
        JsonNode detail = data(mvc.perform(get("/api/admin/audit/" + id).session(manager.session())).andExpect(status().isOk()));
        assertThat(detail.path("detail").asText()).isEqualTo("approved: window 901");
        assertThat(detail.path("outcome").asText()).isEqualTo("SUCCESS");
        mvc.perform(get("/api/admin/audit").param("from", "2999-01-01").session(manager.session()))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(0));
        mvc.perform(get("/api/admin/audit").param("from", "2026-13-01").session(manager.session())).andExpect(status().isBadRequest());
        mvc.perform(get("/api/admin/audit").param("target", "not-allowed").param("from", "2999-01-01").session(manager.session()))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(0));
        mvc.perform(get("/api/admin/audit/999999").session(manager.session())).andExpect(status().isNotFound());
    }

    @Test void modelGovernanceIsRedactedReadOnlyAndCapabilityGuarded() throws Exception {
        // 先清空网关元数据，保证断言只依赖本用例写入的数据。
        jdbc.update("DELETE FROM model_gateway_invocation");
        jdbc.update("DELETE FROM model_gateway_route");
        jdbc.update("DELETE FROM model_gateway_group");
        jdbc.update("DELETE FROM model_gateway_key");
        String hash = "a".repeat(64);
        jdbc.update("INSERT INTO model_gateway_key(id,owner_user_id,name,key_prefix,key_hash,scope) VALUES(901,22,'foundation-key','sk-found',?, 'PERSONAL')", hash);
        jdbc.update("INSERT INTO model_gateway_group(id,owner_user_id,name,slug) VALUES(902,22,'基础组','foundation-group')");
        jdbc.update("INSERT INTO model_gateway_route(id,group_id,connection_id) VALUES(903,902,77)");
        jdbc.update("INSERT INTO model_gateway_invocation(id,key_id,group_slug,model_name,status,total_tokens) VALUES"
                + "(904,901,'foundation-group','m1','SUCCESS',120),(905,901,'foundation-group','m1','SUCCESS',NULL),"
                + "(906,901,'foundation-group','m1','FAILED',NULL)");
        Client manager = admin();
        var result = mvc.perform(get("/api/admin/model-governance").session(manager.session()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.summary.calls").value(3))
                .andExpect(jsonPath("$.data.summary.failures").value(1))
                .andExpect(jsonPath("$.data.summary.unknownUsageCalls").value(1))
                .andExpect(jsonPath("$.data.summary.knownTokens").value(120))
                .andExpect(jsonPath("$.data.keys[0].prefix").value("sk-found"))
                .andExpect(jsonPath("$.data.groups[0].slug").value("foundation-group"))
                .andExpect(jsonPath("$.data.routes[0].healthy").value(true)).andReturn();
        // 只读契约不泄露密钥哈希与明文凭证。
        assertThat(result.getResponse().getContentAsString()).doesNotContain(hash, "key_hash", "keyHash");
        // 只有 admin.users 的专项管理员不能读取模型治理清单。
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(88,'foundation-model-less',?,'admin')", new BCryptPasswordEncoder().encode(PASSWORD));
        accounts.appointPlatformAdmin(new com.smartops.security.SessionUser(11L, "foundation-admin", "admin", "admin", false, 0), 88L, "specialist", List.of("admin.users"));
        Client limited = login("foundation-model-less", PASSWORD, "admin");
        mvc.perform(get("/api/admin/model-governance").session(limited.session())).andExpect(status().isForbidden());
    }

    @Test void workbenchOnlyExposesItemsWithinCallerAuthority() throws Exception {
        jdbc.update("DELETE FROM team_agent_run WHERE team_id=100");
        jdbc.update("DELETE FROM team_member WHERE team_id=100");
        jdbc.update("DELETE FROM team_workspace WHERE id=100");
        jdbc.update("INSERT INTO team_workspace(id,name,owner_id,status) VALUES(100,'foundation-team',11,'active')");
        jdbc.update("INSERT INTO team_member(team_id,user_id,role) VALUES(100,11,'owner')");
        jdbc.update("INSERT INTO team_agent_run(team_id,agent_id,version_id,requester_id,runtime_id,tool_id,read_only,parameters_json,status) "
                + "VALUES(100,1,1,22,'rt-foundation','window.restart',FALSE,'{}','PENDING_APPROVAL')");
        audit.record(new com.smartops.security.SessionUser(22L, "foundation-user", "operator", "user", false, 0), "LOGIN", "22", "DENIED");
        Client manager = admin();
        JsonNode items = data(mvc.perform(get("/api/admin/workbench").session(manager.session())).andExpect(status().isOk())).path("items");
        // 团队批准资格与审计能力都由服务端判定；示例中带团队名，便于直接行动。
        assertThat(items.toString()).contains("APPROVALS", "AUDIT_ATTENTION");
        JsonNode approvals = null;
        for (JsonNode item : items) if (item.path("type").asText().equals("APPROVALS")) approvals = item;
        assertThat(approvals).isNotNull();
        assertThat(approvals.path("count").asLong()).isEqualTo(1);
        assertThat(approvals.path("samples").get(0).path("teamName").asText()).isEqualTo("foundation-team");

        // 专项管理员没有 admin.audit、也不属于该团队：不得看到审计或审批项。
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(99,'foundation-workbench-less',?,'admin')", new BCryptPasswordEncoder().encode(PASSWORD));
        accounts.appointPlatformAdmin(new com.smartops.security.SessionUser(11L, "foundation-admin", "admin", "admin", false, 0), 99L, "specialist", List.of("admin.users"));
        Client limited = login("foundation-workbench-less", PASSWORD, "admin");
        JsonNode limitedItems = data(mvc.perform(get("/api/admin/workbench").session(limited.session())).andExpect(status().isOk())).path("items");
        assertThat(limitedItems.toString()).doesNotContain("APPROVALS", "AUDIT_ATTENTION", "READINESS_GAP");
    }

    private record Client(MockHttpSession session, String csrf) {}
}
