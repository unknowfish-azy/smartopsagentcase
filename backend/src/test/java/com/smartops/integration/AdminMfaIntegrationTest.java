package com.smartops.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
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
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import com.fasterxml.jackson.databind.JsonNode;
import com.smartops.security.*;
import com.smartops.exception.BusinessException;
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:admin_mfa;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AdminMfaIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper json;
    @MockBean com.smartops.service.ModelConnectionService models;
    @MockBean(name = "mfaClock") Clock clock;
    @Autowired TotpService totp;
    @Autowired AdminMfaService mfa;
    @Autowired UserAccountService accounts;
    @Autowired AccountSessionRegistry sessions;
    @org.springframework.boot.test.mock.mockito.SpyBean SecurityAuditService audit;
    private static final String PASSWORD = "IsolatedMfaPassword42!";
    private static final AtomicLong IDS = new AtomicLong(80);
    private long userId;
    private Instant now;
    private String address;

    @BeforeEach
    void seed() {
        now = Instant.parse("2026-10-03T00:00:00Z");
        when(clock.instant()).thenAnswer(invocation -> now);
        userId = IDS.incrementAndGet();
        address = "198.51.100." + (userId % 250 + 1);
        jdbc.queryForList("SELECT id FROM app_user", Long.class).forEach(sessions::revokeUser);
        for (String table : List.of("account_mfa_recovery", "account_mfa", "account_security_notice", "account_security", "security_audit_event")) jdbc.update("DELETE FROM " + table);
        jdbc.update("DELETE FROM app_user");
        String hash = new BCryptPasswordEncoder().encode(PASSWORD);
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(?,'mfa-admin',?,'admin'),(?,'mfa-user',?,'operator')", userId, hash, userId + 10000, hash);
        // SEC-07：SQL 种子的管理员没有治理档案，按迁移回填语义显式建档，
        // 避免依赖“缺档案=ROOT”的旧漏洞语义被能力门禁 403。
        com.smartops.support.TestPlatformProfiles.grantRoot(jdbc, userId);
    }

    @Test
    void authenticatedAdministratorCanStartEnrollmentOnlyAfterPasswordReconfirmation() throws Exception {
        var anonymous = mvc.perform(get("/api/auth/session")).andReturn();
        var session = (MockHttpSession) anonymous.getRequest().getSession(false);
        String csrf = json.readTree(anonymous.getResponse().getContentAsString()).path("data").path("csrfToken").asText();
        mvc.perform(post("/api/auth/login").session(session).header("X-CSRF-TOKEN", csrf).contentType("application/json")
                .content(json.writeValueAsString(java.util.Map.of("username", "mfa-admin", "password", PASSWORD, "portal", "admin"))))
                .andExpect(status().isOk());
        var authenticated = mvc.perform(get("/api/auth/session").session(session)).andReturn();
        csrf = json.readTree(authenticated.getResponse().getContentAsString()).path("data").path("csrfToken").asText();
        mvc.perform(post("/api/admin/mfa/setup").session(session).header("X-CSRF-TOKEN", csrf)
                .header("X-Admin-Password", PASSWORD)).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.secret").isNotEmpty()).andExpect(jsonPath("$.data.challenge").isNotEmpty());
    }

    @Test void enrollmentIsEncryptedRecoveryIsHashedAndOtherSessionsAreRevoked() throws Exception {
        Client admin = admin();
        Client old = admin();
        JsonNode draft = setup(admin);
        JsonNode result = enable(admin, draft);
        assertEquals(10, result.path("recoveryCodes").size());
        assertFalse(jdbc.queryForObject("SELECT secret_encrypted FROM account_mfa WHERE user_id=?", String.class, userId).contains(draft.path("secret").asText()));
        assertFalse(jdbc.queryForObject("SELECT code_hash FROM account_mfa_recovery WHERE user_id=? LIMIT 1", String.class, userId).contains(result.path("recoveryCodes").get(0).asText().replace("-", "")));
        assertTrue(old.session().isInvalid());
        mvc.perform(get("/api/admin/mfa").session(admin.session())).andExpect(status().isOk()).andExpect(jsonPath("$.data.enabled").value(true));
    }

    @Test void pendingIdentityHasNoBusinessPrivilegesAndCompletesOnlyWithFreshCode() throws Exception {
        Client admin = admin(); JsonNode draft = setup(admin); enable(admin, draft);
        Client pending = anonymous();
        JsonNode challenge = login(pending, "mfa-admin", "admin");
        assertTrue(challenge.path("mfaRequired").asBoolean());
        mvc.perform(get("/api/auth/session").session(pending.session())).andExpect(jsonPath("$.data.user").isEmpty());
        mvc.perform(get("/api/admin/users").session(pending.session())).andExpect(status().isUnauthorized());
        complete(pending, challenge, code(draft)).andExpect(status().isBadRequest());
        now = now.plusSeconds(30);
        complete(pending, challenge, code(draft)).andExpect(status().isOk()).andExpect(jsonPath("$.data.portal").value("admin"));
        assertNotEquals(pending.csrf(), refresh(pending).csrf());
        complete(refresh(pending), challenge, code(draft)).andExpect(status().isUnauthorized());
    }

    @Test void userPortalDoesNotBypassAdministratorMfaAndRecoveryCannotBeReused() throws Exception {
        Client admin = admin(); JsonNode codes = enable(admin, setup(admin)).path("recoveryCodes");
        Client pending = anonymous();
        send(pending, post("/api/auth/login"), Map.of("username", "mfa-admin", "password", PASSWORD, "portal", "user"))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/auth/session").session(pending.session())).andExpect(jsonPath("$.data.user").isEmpty());
        JsonNode challenge = login(pending, "mfa-admin", "admin");
        assertTrue(challenge.path("mfaRequired").asBoolean());
        complete(pending, challenge, codes.get(0).asText()).andExpect(status().isOk()).andExpect(jsonPath("$.data.portal").value("admin"));
        Client again = anonymous(); JsonNode next = login(again, "mfa-admin", "admin");
        complete(again, next, codes.get(0).asText()).andExpect(status().isBadRequest());
        assertEquals(9, jdbc.queryForObject("SELECT COUNT(*) FROM account_mfa_recovery WHERE user_id=?", Integer.class, userId));
    }

    @Test void csrfPasswordAndRoleGuardsProtectMfaManagement() throws Exception {
        Client admin = admin();
        mvc.perform(post("/api/admin/mfa/setup").session(admin.session()).header("X-Admin-Password", PASSWORD)).andExpect(status().isForbidden());
        send(admin, post("/api/admin/mfa/setup"), Map.of()).andExpect(status().isForbidden());
        Client ordinary = anonymous(); login(ordinary, "mfa-user", "user"); ordinary = refresh(ordinary);
        send(ordinary, post("/api/admin/mfa/setup").header("X-Admin-Password", PASSWORD), Map.of()).andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/mfa").session(ordinary.session())).andExpect(status().isForbidden());
        mvc.perform(post("/api/auth/mfa/complete").session(admin.session()).contentType("application/json").content("{}" )).andExpect(status().isForbidden());
    }

    @Test void draftIsBoundToSessionAndExpires() throws Exception {
        Client first = admin(); Client other = admin(); JsonNode draft = setup(first);
        management(other, "/enable", Map.of("challenge", draft.path("challenge").asText(), "code", code(draft))).andExpect(status().isConflict());
        now = now.plusSeconds(301);
        management(first, "/enable", Map.of("challenge", draft.path("challenge").asText(), "code", code(draft))).andExpect(status().isConflict());
        assertFalse(mfa.state(userId).enabled());
    }

    @Test void pendingChallengeCannotMoveToAnotherBrowserOrSurviveCancellation() throws Exception {
        Client admin = admin(); JsonNode codes = enable(admin, setup(admin)).path("recoveryCodes");
        Client pending = anonymous(); JsonNode challenge = login(pending, "mfa-admin", "admin");
        complete(anonymous(), challenge, codes.get(0).asText()).andExpect(status().isUnauthorized());
        send(pending, post("/api/auth/mfa/cancel"), Map.of()).andExpect(status().isOk());
        complete(pending, challenge, codes.get(0).asText()).andExpect(status().isUnauthorized());
    }

    @Test void pendingChallengeExpiresAndFiveFailuresInvalidateIt() throws Exception {
        Client admin = admin(); JsonNode draft = setup(admin); enable(admin, draft);
        Client expired = anonymous(); JsonNode old = login(expired, "mfa-admin", "admin");
        now = now.plusSeconds(301);
        complete(expired, old, code(draft)).andExpect(status().isUnauthorized());
        Client pending = anonymous(); JsonNode challenge = login(pending, "mfa-admin", "admin");
        for (int attempt = 0; attempt < 4; attempt++) complete(pending, challenge, "invalid-code").andExpect(status().isBadRequest());
        complete(pending, challenge, "invalid-code").andExpect(status().isTooManyRequests());
        complete(pending, challenge, code(draft)).andExpect(status().isUnauthorized());
        assertEquals(5, jdbc.queryForObject("SELECT COUNT(*) FROM account_security_notice WHERE user_id=? AND kind='MFA_FAILURE'", Integer.class, userId));
    }

    @Test void revokedAccountCannotCompleteAnExistingChallenge() throws Exception {
        Client admin = admin(); JsonNode codes = enable(admin, setup(admin)).path("recoveryCodes");
        Client pending = anonymous(); JsonNode challenge = login(pending, "mfa-admin", "admin");
        jdbc.update("UPDATE app_user SET enabled=FALSE WHERE id=?", userId);
        complete(pending, challenge, codes.get(0).asText()).andExpect(status().isUnauthorized());
    }

    @Test void changingSecurityStateInvalidatesPendingIdentityAndOldRecoveryCodes() throws Exception {
        Client admin = admin(); JsonNode codes = enable(admin, setup(admin)).path("recoveryCodes");
        Client pending = anonymous(); JsonNode challenge = login(pending, "mfa-admin", "admin");
        JsonNode rotated = data(management(admin, "/recovery", Map.of("code", codes.get(0).asText())).andExpect(status().isOk()));
        assertEquals(10, rotated.path("recoveryCodes").size());
        complete(pending, challenge, codes.get(1).asText()).andExpect(status().isUnauthorized());
        Client next = anonymous(); JsonNode nextChallenge = login(next, "mfa-admin", "admin");
        complete(next, nextChallenge, codes.get(1).asText()).andExpect(status().isBadRequest());
        complete(next, nextChallenge, rotated.path("recoveryCodes").get(0).asText()).andExpect(status().isOk());
    }

    @Test void disablingRequiresExistingFactorAndDoesNotChangePassword() throws Exception {
        Client admin = admin(); JsonNode codes = enable(admin, setup(admin)).path("recoveryCodes");
        management(admin, "/disable", Map.of("code", "wrong")).andExpect(status().isBadRequest());
        assertTrue(mfa.state(userId).enabled());
        management(admin, "/disable", Map.of("code", codes.get(0).asText())).andExpect(status().isOk());
        assertFalse(mfa.state(userId).enabled());
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM account_mfa_recovery WHERE user_id=?", Integer.class, userId));
        assertEquals("admin", login(anonymous(), "mfa-admin", "admin").path("portal").asText());
    }

    @Test void remindersBelongOnlyToCurrentAdministrator() throws Exception {
        Client admin = admin(); enable(admin, setup(admin));
        jdbc.update("INSERT INTO account_security_notice(user_id,kind,message) VALUES(?,'PRIVATE','other account')", userId + 1);
        long otherId = jdbc.queryForObject("SELECT MAX(id) FROM account_security_notice", Long.class);
        JsonNode items = data(mvc.perform(get("/api/admin/mfa/notices").session(admin.session())).andExpect(status().isOk()));
        assertEquals(1, items.size());
        send(admin, post("/api/auth/mfa/notices/" + otherId + "/read"), Map.of()).andExpect(status().isNotFound());
        send(admin, post("/api/auth/mfa/notices/" + items.get(0).path("id").asLong() + "/read"), Map.of()).andExpect(status().isOk());
    }

    @Test void concurrentRecoveryConsumptionAllowsExactlyOneSuccess() throws Exception { concurrentConsumption(true); }
    @Test void concurrentTotpConsumptionAllowsExactlyOneSuccess() throws Exception { concurrentConsumption(false); }

    @Test void failedAuditRollsBackSecurityChangesAndRecoveryConsumption() throws Exception {
        Client admin = admin(); JsonNode codes = enable(admin, setup(admin)).path("recoveryCodes");
        doThrow(new IllegalStateException("isolated audit failure")).when(audit).record(any(), eq("MFA_RECOVERY_ROTATE"), anyString(), eq("SUCCESS"));
        management(admin, "/recovery", Map.of("code", codes.get(0).asText())).andExpect(status().isInternalServerError());
        assertEquals(1, mfa.state(userId).version());
        assertEquals(10, mfa.status(new SessionUser(userId, "mfa-admin", "admin")).recoveryCodesRemaining());
        Client pending = anonymous(); JsonNode challenge = login(pending, "mfa-admin", "admin");
        complete(pending, challenge, codes.get(0).asText()).andExpect(status().isOk());
    }

    @Test void failedLoginAuditDoesNotConsumeRecoveryOrDestroyPendingChallenge() throws Exception {
        Client admin = admin(); JsonNode codes = enable(admin, setup(admin)).path("recoveryCodes");
        Client pending = anonymous(); JsonNode challenge = login(pending, "mfa-admin", "admin");
        doThrow(new IllegalStateException("isolated LOGIN audit failure")).when(audit).record(any(), eq("LOGIN"), anyString(), eq("SUCCESS"));
        complete(pending, challenge, codes.get(0).asText()).andExpect(status().isInternalServerError());
        assertEquals(10, mfa.status(new SessionUser(userId, "mfa-admin", "admin")).recoveryCodesRemaining());
        doCallRealMethod().when(audit).record(any(), eq("LOGIN"), anyString(), eq("SUCCESS"));
        complete(pending, challenge, codes.get(0).asText()).andExpect(status().isOk());
    }

    @Test void concurrentReadCannotInvalidateSessionDuringVersionHandoff() throws Exception {
        var session = new PausingSession();
        var first = mvc.perform(get("/api/auth/session").session(session)).andReturn();
        Client admin = new Client(session, json.readTree(first.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
        login(admin, "mfa-admin", "admin");
        Client authenticated = refresh(admin);
        JsonNode codes = enable(authenticated, setup(authenticated)).path("recoveryCodes");
        session.armed = true;
        var pool = Executors.newFixedThreadPool(2);
        try {
            var mutation = pool.submit(() -> management(authenticated, "/recovery", Map.of("code", codes.get(0).asText())).andExpect(status().isOk()));
            assertTrue(session.beforeStamp.await(5, TimeUnit.SECONDS));
            var read = pool.submit(() -> mvc.perform(get("/api/admin/mfa").session(session)).andExpect(status().isOk()));
            assertThrows(java.util.concurrent.TimeoutException.class, () -> read.get(500, TimeUnit.MILLISECONDS));
            session.release.countDown();
            mutation.get(10, TimeUnit.SECONDS); read.get(10, TimeUnit.SECONDS);
            assertFalse(session.isInvalid());
        } finally { session.release.countDown(); pool.shutdownNow(); }
    }

    private static final class PausingSession extends MockHttpSession {
        volatile boolean armed;
        final CountDownLatch beforeStamp = new CountDownLatch(1), release = new CountDownLatch(1);
        @Override public void setAttribute(String name, Object value) {
            if (armed && AdminMfaService.SESSION_VERSION.equals(name)) {
                beforeStamp.countDown();
                try { if (!release.await(10, TimeUnit.SECONDS)) throw new IllegalStateException("handoff test timed out"); }
                catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw new IllegalStateException(interrupted); }
            }
            super.setAttribute(name, value);
        }
    }

    private void concurrentConsumption(boolean recovery) throws Exception {
        Client admin = admin(); JsonNode draft = setup(admin); JsonNode codes = enable(admin, draft).path("recoveryCodes");
        now = now.plusSeconds(30);
        String supplied = recovery ? codes.get(0).asText() : code(draft);
        SessionUser user = accounts.authenticate("mfa-admin", PASSWORD, address, "admin");
        var pool = Executors.newFixedThreadPool(2); var start = new CountDownLatch(1);
        java.util.concurrent.Callable<Integer> attempt = () -> {
            start.await();
            try { mfa.verifyLogin(user, 1, supplied, address); return 200; }
            catch (BusinessException rejected) { return rejected.getCode(); }
        };
        try {
            var first = pool.submit(attempt); var second = pool.submit(attempt); start.countDown();
            var results = new java.util.ArrayList<>(List.of(first.get(10, TimeUnit.SECONDS), second.get(10, TimeUnit.SECONDS)));
            results.sort(Integer::compareTo); assertEquals(List.of(200, 400), results);
        } finally { pool.shutdownNow(); }
    }

    private Client anonymous() throws Exception {
        var result = mvc.perform(get("/api/auth/session")).andReturn();
        return new Client((MockHttpSession) result.getRequest().getSession(false), json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }
    private Client refresh(Client client) throws Exception {
        var result = mvc.perform(get("/api/auth/session").session(client.session())).andReturn();
        return new Client(client.session(), json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }
    private Client admin() throws Exception { Client client = anonymous(); login(client, "mfa-admin", "admin"); return refresh(client); }
    private JsonNode login(Client client, String username, String portal) throws Exception {
        return data(send(client, post("/api/auth/login"), Map.of("username", username, "password", PASSWORD, "portal", portal)).andExpect(status().isOk()));
    }
    private JsonNode setup(Client client) throws Exception { return data(management(client, "/setup", Map.of()).andExpect(status().isOk()).andExpect(header().string("Cache-Control", "no-store"))); }
    private JsonNode enable(Client client, JsonNode draft) throws Exception {
        return data(management(client, "/enable", Map.of("challenge", draft.path("challenge").asText(), "code", code(draft))).andExpect(status().isOk()));
    }
    private String code(JsonNode draft) { return totp.code(draft.path("secret").asText(), now.getEpochSecond() / 30); }
    private ResultActions management(Client client, String path, Map<String, ?> body) throws Exception {
        return send(client, post("/api/admin/mfa" + path).header("X-Admin-Password", PASSWORD), body);
    }
    private ResultActions complete(Client client, JsonNode challenge, String code) throws Exception {
        return send(client, post("/api/auth/mfa/complete"), Map.of("challenge", challenge.path("challenge").asText(), "code", code));
    }
    private ResultActions send(Client client, MockHttpServletRequestBuilder request, Map<String, ?> body) throws Exception {
        return mvc.perform(request.session(client.session()).header("X-CSRF-TOKEN", client.csrf()).with(value -> { value.setRemoteAddr(address); return value; })
                .contentType("application/json").content(json.writeValueAsString(body)));
    }
    private JsonNode data(ResultActions action) throws Exception { return json.readTree(action.andReturn().getResponse().getContentAsString()).path("data"); }
    private record Client(MockHttpSession session, String csrf) {}
}
