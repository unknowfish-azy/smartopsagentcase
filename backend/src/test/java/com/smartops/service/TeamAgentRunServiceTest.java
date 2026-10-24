package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

class TeamAgentRunServiceTest {
    private JdbcTemplate jdbc;
    private TeamAgentRunService service;
    private TeamAgentService agents;
    private TeamResourceAuthorizer authorizer;

    @BeforeEach
    void setUp() {
        jdbc = new JdbcTemplate(new DriverManagerDataSource("jdbc:h2:mem:team-run-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        jdbc.execute("CREATE TABLE team_agent_run (id BIGINT AUTO_INCREMENT PRIMARY KEY, team_id BIGINT, agent_id BIGINT, version_id BIGINT, requester_id BIGINT, runtime_id VARCHAR(128), tool_id VARCHAR(128), read_only BOOLEAN, parameters_json CLOB, status VARCHAR(32), previewed_by BIGINT, preview_digest VARCHAR(64), approved_by BIGINT, grant_token VARCHAR(128), grant_expires_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, decision_basis VARCHAR(800))");
        authorizer = mock(TeamResourceAuthorizer.class);
        agents = mock(TeamAgentService.class);
        when(agents.availableTools(any(), eq(10L), eq(7L))).thenReturn(List.of(
                new OperationToolService.ToolDescriptor("host-health", true, "LOW", false, "HOST_HEALTH"),
                new OperationToolService.ToolDescriptor("service-restart", false, "HIGH", true, "SERVICE_RESTART")));
        when(agents.detail(any(), eq(10L), eq(7L))).thenReturn(new TeamAgentService.AgentDetail(
                new TeamAgentService.Agent(7, 10, "Agent", "", "PUBLISHED", 11L, 1, 1),
                null, new TeamAgentService.Version(11, 7, 1, "prompt", "[\"host-health\",\"service-restart\"]", "PUBLISHED")));
        when(authorizer.requireMember(any(), eq(20L), anyString())).thenThrow(new BusinessException(403, "TEAM_ACCESS_FORBIDDEN"));
        when(authorizer.requireMember(argThat(user -> user != null && user.id() == 2), eq(10L), eq("approve")))
                .thenThrow(new BusinessException(403, "TEAM_CAPABILITY_FORBIDDEN"));
        service = new TeamAgentRunService(jdbc, authorizer, agents, new ObjectMapper(), Clock.systemUTC(), mock(com.smartops.security.SecurityAuditService.class));
    }

    @Test
    void approvalRecordsDecisionBasis() {
        var member = user(2, "operator");
        var mutation = service.create(member, 10, 7, 11, "runtime-1", "service-restart", Map.of("service", "api"));
        service.markPreview(user(1, "owner"), mutation.id(), "digest");

        // 不带依据：兼容旧行为，basis 为空
        var plain = service.approve(user(1, "owner"), mutation.id());
        assertThat(plain.decisionBasis()).isNull();

        // 带依据：能回答"基于什么批的"
        var another = service.create(member, 10, 7, 11, "runtime-1", "service-restart", Map.of("service", "web"));
        service.markPreview(user(1, "owner"), another.id(), "digest-2");
        var withBasis = service.approve(user(1, "owner"), another.id(), "依据告警 #42 的 AI 研判与预览摘要 digest-2");
        assertThat(withBasis.decisionBasis()).contains("告警 #42");
        assertThat(withBasis.status()).isEqualTo("APPROVED");

        // 空白依据会被规整为 null，避免存下一串空格冒充"有依据"
        var third = service.create(member, 10, 7, 11, "runtime-1", "service-restart", Map.of("service", "db"));
        service.markPreview(user(1, "owner"), third.id(), "digest-3");
        assertThat(service.approve(user(1, "owner"), third.id(), "   ").decisionBasis()).isNull();
    }

    @Test
    void readOnlyRunIsImmediatelyApprovedButMutationNeedsApprovalAndOneTimeGrant() {
        var member = user(2, "operator");
        var read = service.create(member, 10, 7, 11, "runtime-1", "host-health", Map.of("lines", "20"));
        assertThat(read.status()).isEqualTo("APPROVED");
        var mutation = service.create(member, 10, 7, 11, "runtime-1", "service-restart", Map.of("service", "api"));
        assertThat(mutation.status()).isEqualTo("PENDING_APPROVAL");
        assertThatThrownBy(() -> service.consumeGrant(member, mutation.id(), null))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_RUN_APPROVAL_REQUIRED");
        assertThatThrownBy(() -> service.approve(user(1, "owner"), mutation.id()))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_RUN_PREVIEW_REQUIRED");
        service.markPreview(user(1, "owner"), mutation.id(), "digest");
        var approved = service.approve(user(1, "owner"), mutation.id());
        assertThat(approved.status()).isEqualTo("APPROVED");
        assertThat(approved.grantToken()).isNotBlank();
        assertThatThrownBy(() -> service.consumeGrant(member, mutation.id(), "changed-command"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_RUN_PREVIEW_CHANGED");
        var consumed = service.consumeGrant(member, mutation.id(), "digest");
        assertThat(consumed.toolId()).isEqualTo("service-restart");
        assertThatThrownBy(() -> service.consumeGrant(member, mutation.id(), "digest"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_RUN_GRANT_USED");
    }

    @Test
    void requesterCannotApproveAndUnknownOrCrossTeamToolIsRejected() {
        var member = user(2, "operator");
        var run = service.create(member, 10, 7, 11, "runtime-1", "service-restart", Map.of("service", "api"));
        assertThatThrownBy(() -> service.approve(member, run.id()))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_CAPABILITY_FORBIDDEN");
        assertThatThrownBy(() -> service.create(member, 20, 7, 11, "runtime-1", "service-restart", Map.of()))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_ACCESS_FORBIDDEN");
        assertThatThrownBy(() -> service.create(member, 10, 7, 11, "runtime-1", "unknown", Map.of()))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_TOOL_NOT_ALLOWED");
    }

    @Test
    void revokedMemberAndChangedVersionCannotConsumeApprovedRun() {
        var member = user(2, "operator");
        var run = service.create(member, 10, 7, 11, "runtime-1", "service-restart", Map.of("service", "api"));
        service.markPreview(user(1, "owner"), run.id(), "digest");
        service.approve(user(1, "owner"), run.id());
        when(authorizer.requireMember(member, 10, "run")).thenThrow(new BusinessException(403, "TEAM_ACCESS_FORBIDDEN"));
        assertThatThrownBy(() -> service.consumeGrant(member, run.id(), "digest"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_ACCESS_FORBIDDEN");
        reset(authorizer);
        when(agents.detail(any(), eq(10L), eq(7L))).thenReturn(new TeamAgentService.AgentDetail(
                new TeamAgentService.Agent(7, 10, "Agent", "", "PUBLISHED", 12L, 2, 1), null,
                new TeamAgentService.Version(12, 7, 2, "changed", "[\"service-restart\"]", "PUBLISHED")));
        assertThatThrownBy(() -> service.consumeGrant(member, run.id(), "digest"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_AGENT_VERSION_CHANGED");
    }

    @Test
    void expiredMutationGrantCannotExecute() {
        var member = user(2, "operator");
        var run = service.create(member, 10, 7, 11, "runtime-1", "service-restart", Map.of("service", "api"));
        service.markPreview(user(1, "owner"), run.id(), "digest");
        service.approve(user(1, "owner"), run.id());
        var later = new TeamAgentRunService(jdbc, authorizer, agents, new ObjectMapper(),
                Clock.fixed(Instant.now().plusSeconds(600), ZoneOffset.UTC), mock(com.smartops.security.SecurityAuditService.class));
        assertThatThrownBy(() -> later.consumeGrant(member, run.id(), "digest"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_RUN_GRANT_INVALID");
    }

    @Test
    void readOnlyGrantExpiresAndRemovedToolCannotExecute() {
        var member = user(2, "operator");
        var read = service.create(member, 10, 7, 11, "runtime-1", "host-health", Map.of());
        var later = new TeamAgentRunService(jdbc, authorizer, agents, new ObjectMapper(),
                Clock.fixed(Instant.now().plusSeconds(600), ZoneOffset.UTC), mock(com.smartops.security.SecurityAuditService.class));
        assertThatThrownBy(() -> later.consumeGrant(member, read.id(), null))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_RUN_GRANT_INVALID");
        var mutation = service.create(member, 10, 7, 11, "runtime-1", "service-restart", Map.of("service", "api"));
        service.markPreview(user(1, "owner"), mutation.id(), "digest");
        service.approve(user(1, "owner"), mutation.id());
        when(agents.availableTools(any(), eq(10L), eq(7L))).thenReturn(List.of(
                new OperationToolService.ToolDescriptor("host-health", true, "LOW", false, "HOST_HEALTH")));
        assertThatThrownBy(() -> service.consumeGrant(member, mutation.id(), "digest"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_TOOL_NOT_ALLOWED");
    }

    private SessionUser user(long id, String role) { return new SessionUser(id, "u" + id, role, "user", false, 0); }
}
