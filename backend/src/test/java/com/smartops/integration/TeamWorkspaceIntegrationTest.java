package com.smartops.integration;

import com.fasterxml.jackson.databind.JsonNode;
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
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import java.util.List;
import com.smartops.service.TeamWorkspaceService;
import com.smartops.security.SessionUser;
import com.smartops.security.SecurityAuditService;
import com.smartops.exception.BusinessException;
import org.springframework.boot.test.mock.mockito.SpyBean;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {"spring.datasource.url=jdbc:h2:mem:team_workspace;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE", "spring.datasource.hikari.transaction-isolation=TRANSACTION_REPEATABLE_READ"})
@AutoConfigureMockMvc
@ActiveProfiles("test")
class TeamWorkspaceIntegrationTest {
    @Autowired MockMvc mvc;
    @SpyBean JdbcTemplate jdbc;
    @Autowired ObjectMapper json;
    @MockBean com.smartops.service.ModelConnectionService models;
    @Autowired TeamWorkspaceService teams;
    @SpyBean SecurityAuditService audit;
    private static final AtomicLong IDS = new AtomicLong(40000);
    private static final String PASSWORD = "WorkspaceTestPassword42!";
    private static final String HASH = new BCryptPasswordEncoder().encode(PASSWORD);
    private long userId;
    private String username;

    @BeforeEach void seed() {
        userId = IDS.incrementAndGet();
        username = "workspace-" + userId;
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(?,?,?,'operator')", userId, username, HASH);
    }

    @Test void userCanCreatePrivateTeamAndListOnlyTheirMemberships() throws Exception {
        Client owner = login(username, "user");
        JsonNode created = data(send(owner, post("/api/teams"), Map.of("name", "测试团队", "description", "私有工作空间"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.role").value("owner")));
        mvc.perform(get("/api/teams").session(owner.session())).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.items[0].id").value(created.path("id").asLong()));
        User other = other("operator", "user");
        mvc.perform(get("/api/teams").session(other.client().session()).header("X-User-Id", userId)).andExpect(jsonPath("$.data.total").value(0));
        mvc.perform(get("/api/teams/" + created.path("id").asLong()).session(other.client().session())).andExpect(status().isNotFound());
    }

    @Test void inviteRequiresExplicitAcceptanceAndCannotBeReplayedOrStolen() throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User member = other("operator", "user"); User outsider = other("operator", "user");
        long invitation = invite(owner, id, member, "member");
        mvc.perform(get("/api/teams/" + id).session(member.client().session())).andExpect(status().isNotFound());
        respond(outsider.client(), invitation, true).andExpect(status().isNotFound());
        respond(member.client(), invitation, true).andExpect(status().isOk());
        respond(member.client(), invitation, true).andExpect(status().isConflict());
        mvc.perform(get("/api/teams/" + id).session(member.client().session())).andExpect(jsonPath("$.data.team.role").value("member"));
        assertEquals(2, jdbc.queryForObject("SELECT COUNT(*) FROM team_member WHERE team_id=?", Integer.class, id));
    }

    @Test void csrfAndAnonymousRequestsAreRejected() throws Exception {
        mvc.perform(get("/api/teams")).andExpect(status().isUnauthorized());
        Client owner = login(username, "user");
        mvc.perform(post("/api/teams").session(owner.session()).contentType("application/json").content("{\"name\":\"forbidden\"}")).andExpect(status().isForbidden());
        send(owner, post("/api/teams"), Map.of("name", " ")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/teams?page=0").session(owner.session())).andExpect(status().isBadRequest());
    }

    @Test void viewersCannotEditInviteOrRemoveOtherMembersButCanLeave() throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User viewer = other("operator", "user"); join(owner, id, viewer, "viewer");
        send(viewer.client(), put("/api/teams/" + id), Map.of("name", "forbidden")).andExpect(status().isForbidden());
        send(viewer.client(), post("/api/teams/" + id + "/invitations"), Map.of("username", username, "role", "member")).andExpect(status().isForbidden());
        send(viewer.client(), delete("/api/teams/" + id + "/members/" + userId), Map.of()).andExpect(status().isForbidden());
        send(viewer.client(), delete("/api/teams/" + id + "/members/" + viewer.id()), Map.of()).andExpect(status().isOk());
        mvc.perform(get("/api/teams/" + id).session(viewer.client().session())).andExpect(status().isNotFound());
    }

    @Test void teamAdminCannotGrantOrManageAdminAndOwnerCannotBeRemoved() throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User admin = other("operator", "user"); join(owner, id, admin, "admin");
        User member = other("operator", "user"); join(owner, id, member, "member");
        send(admin.client(), put("/api/teams/" + id + "/members/" + member.id()), Map.of("role", "admin")).andExpect(status().isForbidden());
        send(owner, put("/api/teams/" + id + "/members/" + member.id()), Map.of("role", "owner")).andExpect(status().isBadRequest());
        send(owner, delete("/api/teams/" + id + "/members/" + userId), Map.of()).andExpect(status().isForbidden());
        send(owner, put("/api/teams/" + id + "/members/" + member.id()), Map.of("role", "viewer")).andExpect(status().isOk());
        mvc.perform(get("/api/admin/teams").session(admin.client().session())).andExpect(status().isForbidden());
    }

    @Test void revokedExpiredAndDeclinedInvitationsNeverGrantMembership() throws Exception {
        Client owner = login(username, "user"); long id = create(owner); User user = other("operator", "user");
        long invitation = invite(owner, id, user, "member");
        send(owner, delete("/api/teams/" + id + "/invitations/" + invitation), Map.of()).andExpect(status().isOk());
        respond(user.client(), invitation, true).andExpect(status().isConflict());
        invitation = invite(owner, id, user, "member");
        jdbc.update("UPDATE team_invitation SET expires_at=? WHERE id=?", java.sql.Timestamp.from(java.time.Instant.now().minusSeconds(1)), invitation);
        respond(user.client(), invitation, true).andExpect(status().isConflict());
        invitation = invite(owner, id, user, "member");
        respond(user.client(), invitation, false).andExpect(status().isOk());
        respond(user.client(), invitation, true).andExpect(status().isConflict());
    }

    @Test void removingInviterCancelsOutstandingInvitationsAndMembershipImmediately() throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User admin = other("operator", "user"); join(owner, id, admin, "admin");
        User recipient = other("operator", "user"); long invitation = invite(admin.client(), id, recipient, "member");
        send(owner, delete("/api/teams/" + id + "/members/" + admin.id()), Map.of()).andExpect(status().isOk());
        respond(recipient.client(), invitation, true).andExpect(status().isConflict());
        mvc.perform(get("/api/teams/" + id).session(admin.client().session())).andExpect(status().isNotFound());
    }

    @Test void administratorManagesMetadataOnlyAndFreezeBlocksWritesAndAcceptance() throws Exception {
        Client owner = login(username, "user"); long id = create(owner); User invited = other("operator", "user");
        long invitation = invite(owner, id, invited, "member");
        User platform = other("admin", "admin");
        mvc.perform(get("/api/admin/teams?q=隔离团队").session(platform.client().session())).andExpect(status().isOk());
        mvc.perform(get("/api/admin/teams/" + id + "/members").session(platform.client().session())).andExpect(status().isOk()).andExpect(jsonPath("$.data[0].passwordHash").doesNotExist());
        mvc.perform(get("/api/teams/" + id).session(platform.client().session())).andExpect(status().isNotFound());
        send(platform.client(), put("/api/admin/teams/" + id + "/status"), Map.of("status", "frozen")).andExpect(status().isForbidden());
        send(platform.client(), put("/api/admin/teams/" + id + "/status").header("X-Admin-Password", PASSWORD), Map.of("status", "frozen")).andExpect(status().isOk());
        respond(invited.client(), invitation, true).andExpect(status().isForbidden());
        send(owner, put("/api/teams/" + id), Map.of("name", "forbidden")).andExpect(status().isForbidden());
        mvc.perform(get("/api/teams/" + id).session(owner.session())).andExpect(jsonPath("$.data.team.status").value("frozen"));
        send(platform.client(), put("/api/admin/teams/" + id + "/status").header("X-Admin-Password", PASSWORD), Map.of("status", "active")).andExpect(status().isOk());
        respond(invited.client(), invitation, true).andExpect(status().isOk());
    }

    @Test void userPortalAdminCannotUseGovernanceAndForeignInvitationCannotBeCancelled() throws Exception {
        Client owner = login(username, "user"); long first = create(owner); long second = create(owner);
        User invited = other("operator", "user"); long invitation = invite(owner, first, invited, "member");
        send(owner, delete("/api/teams/" + second + "/invitations/" + invitation), Map.of()).andExpect(status().isNotFound());
        long platformId = IDS.incrementAndGet(); String platformName = "workspace-" + platformId;
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(?,?,?,?)", platformId, platformName, HASH, "admin");
        send(owner, post("/api/auth/login"), Map.of("username", platformName, "password", PASSWORD, "portal", "user")).andExpect(status().isForbidden());
    }

    @Test void auditFailureRollsBackTeamCreationAndMembership() {
        var actor = new SessionUser(userId, username, "operator");
        doThrow(new BusinessException(503, "isolated audit failure")).when(audit).record(any(), eq("TEAM_CREATE"), anyString(), eq("SUCCESS"));
        try {
            assertThrows(BusinessException.class, () -> teams.create(actor, "rollback", ""));
            assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM team_workspace WHERE owner_id=?", Integer.class, userId));
            assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM team_member WHERE user_id=?", Integer.class, userId));
        } finally { reset(audit); }
    }

    @Test void concurrentAcceptanceOnlyCreatesOneMembership() throws Exception {
        Client owner = login(username, "user"); long id = create(owner); User invited = other("operator", "user");
        long invitation = invite(owner, id, invited, "member");
        var actor = new SessionUser(invited.id(), invited.name(), "operator");
        var pool = java.util.concurrent.Executors.newFixedThreadPool(2);
        var start = new java.util.concurrent.CountDownLatch(1);
        java.util.concurrent.Callable<Integer> attempt = () -> { start.await(); try { teams.respond(actor, invitation, true); return 200; } catch (BusinessException error) { return error.getCode(); } };
        try {
            var first = pool.submit(attempt); var second = pool.submit(attempt); start.countDown();
            var statuses = new java.util.ArrayList<>(List.of(first.get(10, java.util.concurrent.TimeUnit.SECONDS), second.get(10, java.util.concurrent.TimeUnit.SECONDS)));
            statuses.sort(Integer::compareTo); assertEquals(List.of(200, 409), statuses);
        } finally { pool.shutdownNow(); }
    }

    @Test void disabledInviterAndDuplicateInvitationAreRejected() throws Exception {
        Client owner = login(username, "user"); long id = create(owner); User invited = other("operator", "user");
        long invitation = invite(owner, id, invited, "viewer");
        send(owner, post("/api/teams/" + id + "/invitations"), Map.of("username", invited.name(), "role", "viewer")).andExpect(status().isConflict());
        jdbc.update("UPDATE app_user SET enabled=FALSE WHERE id=?", userId);
        respond(invited.client(), invitation, true).andExpect(status().isConflict());
    }

    @Test void ownerQuotaIsEnforced() {
        var actor = new SessionUser(userId, username, "operator");
        for (int index = 0; index < 10; index++) teams.create(actor, "quota-" + index, "");
        assertEquals(409, assertThrows(BusinessException.class, () -> teams.create(actor, "overflow", "")).getCode());
    }

    @Test void frozenTeamAllowsSelfExitButNoOtherMembershipChanges() throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User member = other("operator", "user"); join(owner, id, member, "member");
        jdbc.update("UPDATE team_workspace SET status='frozen' WHERE id=?", id);
        send(owner, delete("/api/teams/" + id + "/members/" + member.id()), Map.of()).andExpect(status().isForbidden());
        send(member.client(), delete("/api/teams/" + id + "/members/" + member.id()), Map.of()).andExpect(status().isOk());
    }

    @Test void outsidersCannotDiscoverFrozenStatusThroughMutationEndpoints() throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User outsider = other("operator", "user");
        jdbc.update("UPDATE team_workspace SET status='frozen' WHERE id=?", id);
        send(outsider.client(), put("/api/teams/" + id), Map.of("name", "forbidden")).andExpect(status().isNotFound());
        send(outsider.client(), post("/api/teams/" + id + "/invitations"), Map.of("username", username, "role", "member")).andExpect(status().isNotFound());
        send(outsider.client(), put("/api/teams/" + id + "/members/" + userId), Map.of("role", "member")).andExpect(status().isNotFound());
        send(outsider.client(), delete("/api/teams/" + id + "/invitations/99999"), Map.of()).andExpect(status().isNotFound());
    }

    @Test void demotionRevokesIssuedInvitationsAndAuditCanFilterTeamEvents() throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User admin = other("operator", "user"); join(owner, id, admin, "admin");
        User recipient = other("operator", "user"); long invitation = invite(admin.client(), id, recipient, "viewer");
        send(owner, put("/api/teams/" + id + "/members/" + admin.id()), Map.of("role", "member")).andExpect(status().isOk());
        respond(recipient.client(), invitation, true).andExpect(status().isConflict());
        User platform = other("admin", "admin");
        mvc.perform(get("/api/admin/audit?action=TEAM_MEMBER_ROLE").session(platform.client().session())).andExpect(status().isOk());
    }

    @Test void staleAdministratorCannotGovernAfterAccountDisable() throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User admin = other("admin", "admin");
        var stale = new SessionUser(admin.id(), admin.name(), "admin");
        jdbc.update("UPDATE app_user SET enabled=FALSE WHERE id=?", admin.id());
        assertEquals(401, assertThrows(BusinessException.class, () -> teams.setStatus(stale, id, "frozen")).getCode());
        assertEquals("active", jdbc.queryForObject("SELECT status FROM team_workspace WHERE id=?", String.class, id));
    }

    @Test void invitationAcceptanceSeesCancellationCommittedAfterItsFirstRead() throws Exception {
        acceptanceMustObserveChange(false);
    }

    @Test void invitationAcceptanceSeesFreezeCommittedAfterItsFirstRead() throws Exception {
        acceptanceMustObserveChange(true);
    }

    private void acceptanceMustObserveChange(boolean freeze) throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User recipient = other("operator", "user"); long invitation = invite(owner, id, recipient, "member");
        var read = new java.util.concurrent.CountDownLatch(1); var release = new java.util.concurrent.CountDownLatch(1);
        doAnswer(invocation -> {
            Object result = invocation.callRealMethod(); read.countDown();
            if (!release.await(10, java.util.concurrent.TimeUnit.SECONDS)) throw new IllegalStateException("snapshot regression timed out");
            return result;
        }).when(jdbc).queryForList(eq("SELECT team_id FROM team_invitation WHERE id=? AND invitee_id=?"), eq(Long.class), eq(invitation), eq(recipient.id()));
        var pool = java.util.concurrent.Executors.newSingleThreadExecutor();
        try {
            var result = pool.submit(() -> { try { teams.respond(new SessionUser(recipient.id(), recipient.name(), "operator"), invitation, true); return 200; } catch (BusinessException rejected) { return rejected.getCode(); } });
            assertTrue(read.await(10, java.util.concurrent.TimeUnit.SECONDS));
            if (freeze) jdbc.update("UPDATE team_workspace SET status='frozen' WHERE id=?", id);
            else teams.cancelInvite(new SessionUser(userId, username, "operator"), id, invitation);
            release.countDown();
            assertEquals(freeze ? 403 : 409, result.get(10, java.util.concurrent.TimeUnit.SECONDS));
            assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM team_member WHERE team_id=? AND user_id=?", Integer.class, id, recipient.id()));
        } finally { release.countDown(); pool.shutdownNow(); reset(jdbc); }
    }

    @Test void inviteLinkJoinsOnceAndCanBeRevoked() throws Exception {
        Client owner = login(username, "user"); long id = create(owner); User recipient = other("operator", "user"); User late = other("operator", "user");
        JsonNode link = data(send(owner, post("/api/teams/" + id + "/invite-links"), Map.of("role", "member")).andExpect(status().isOk()));
        String token = link.path("token").asText();
        mvc.perform(get("/api/teams/invite-links/" + token).session(recipient.client().session())).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.valid").value(true)).andExpect(jsonPath("$.data.member").value(false))
                .andExpect(jsonPath("$.data.role").value("member"));
        send(recipient.client(), post("/api/teams/invite-links/" + token + "/accept"), Map.of()).andExpect(status().isOk());
        mvc.perform(get("/api/teams/" + id).session(recipient.client().session())).andExpect(jsonPath("$.data.team.role").value("member"));
        send(late.client(), post("/api/teams/invite-links/" + token + "/accept"), Map.of()).andExpect(status().isConflict());
        send(recipient.client(), post("/api/teams/" + id + "/invite-links"), Map.of("role", "viewer")).andExpect(status().isForbidden());
        JsonNode second = data(send(owner, post("/api/teams/" + id + "/invite-links"), Map.of("role", "viewer")).andExpect(status().isOk()));
        send(owner, delete("/api/teams/" + id + "/invite-links/" + second.path("id").asLong()), Map.of()).andExpect(status().isOk());
        send(late.client(), post("/api/teams/invite-links/" + second.path("token").asText() + "/accept"), Map.of()).andExpect(status().isConflict());
    }

    @Test void sharedKnowledgeIsReadableByTeamMembersOnly() throws Exception {
        Client owner = login(username, "user"); long id = create(owner);
        User member = other("operator", "user"); join(owner, id, member, "member");
        User outsider = other("operator", "user");
        Timestamp now = Timestamp.from(Instant.now());
        jdbc.update("INSERT INTO personal_knowledge_library(user_id,name,description,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", userId, "共享知识库", "只读共享", "ACTIVE", now, now);
        long library = jdbc.queryForObject("SELECT MAX(id) FROM personal_knowledge_library WHERE user_id=?", Long.class, userId);
        assertEquals(userId, jdbc.queryForObject("SELECT user_id FROM personal_knowledge_library WHERE id=?", Long.class, library));
        jdbc.update("INSERT INTO personal_knowledge_entry(library_id,user_id,title,summary,content_markdown,source_type,verification_status,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                library, userId, "Nginx 502 排查", "上游超时", "# 排查步骤", "MANUAL", "VERIFIED", 1, now, now);
        send(owner, post("/api/teams/" + id + "/shares"), Map.of("resourceType", "knowledge", "resourceId", library)).andExpect(status().isOk());
        mvc.perform(get("/api/teams/" + id + "/shares").session(member.client().session())).andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].resourceId").value(library)).andExpect(jsonPath("$.data[0].entryCount").value(1));
        mvc.perform(get("/api/teams/" + id + "/shares/knowledge/" + library + "/entries").session(member.client().session())).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(1)).andExpect(jsonPath("$.data.items[0].title").value("Nginx 502 排查"));
        mvc.perform(get("/api/teams/" + id + "/shares").session(outsider.client().session())).andExpect(status().isForbidden());
        send(member.client(), post("/api/teams/" + id + "/shares"), Map.of("resourceType", "knowledge", "resourceId", library)).andExpect(status().isForbidden());
        send(owner, delete("/api/teams/" + id + "/shares/knowledge/" + library), Map.of()).andExpect(status().isOk());
        mvc.perform(get("/api/teams/" + id + "/shares/knowledge/" + library + "/entries").session(member.client().session())).andExpect(status().isNotFound());
    }

    private long create(Client owner) throws Exception { return data(send(owner, post("/api/teams"), Map.of("name", "隔离团队", "description", "不共享个人资源")).andExpect(status().isOk())).path("id").asLong(); }
    private User other(String role, String portal) throws Exception {
        long id = IDS.incrementAndGet(); String name = "workspace-" + id;
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(?,?,?,?)", id, name, HASH, role);
        // SEC-07：平台管理能力来自治理档案；SQL 种子的管理员按迁移回填语义显式建档。
        if ("admin".equals(role)) com.smartops.support.TestPlatformProfiles.grantRoot(jdbc, id);
        return new User(id, name, login(name, portal));
    }
    private long invite(Client owner, long id, User user, String role) throws Exception {
        send(owner, post("/api/teams/" + id + "/invitations"), Map.of("username", user.name(), "role", role)).andExpect(status().isOk());
        return jdbc.queryForObject("SELECT id FROM team_invitation WHERE team_id=? AND invitee_id=?", Long.class, id, user.id());
    }
    private void join(Client owner, long id, User user, String role) throws Exception { respond(user.client(), invite(owner, id, user, role), true).andExpect(status().isOk()); }
    private ResultActions respond(Client client, long id, boolean accept) throws Exception { return send(client, post("/api/teams/invitations/" + id + "/respond"), Map.of("accept", accept)); }
    private record User(long id, String name, Client client) {}

    private Client login(String name, String portal) throws Exception {
        var result = mvc.perform(get("/api/auth/session")).andReturn();
        var session = (MockHttpSession) result.getRequest().getSession(false);
        String csrf = json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText();
        send(new Client(session, csrf), post("/api/auth/login"), Map.of("username", name, "password", PASSWORD, "portal", portal)).andExpect(status().isOk());
        result = mvc.perform(get("/api/auth/session").session(session)).andReturn();
        return new Client(session, json.readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText());
    }
    private ResultActions send(Client client, MockHttpServletRequestBuilder request, Map<String, ?> body) throws Exception {
        return mvc.perform(request.session(client.session()).header("X-CSRF-TOKEN", client.csrf())
                .with(value -> { value.setRemoteAddr("192.0.2." + (userId % 250 + 1)); return value; })
                .contentType("application/json").content(json.writeValueAsString(body)));
    }
    private JsonNode data(ResultActions action) throws Exception { return json.readTree(action.andReturn().getResponse().getContentAsString()).path("data"); }
    private record Client(MockHttpSession session, String csrf) {}
}
