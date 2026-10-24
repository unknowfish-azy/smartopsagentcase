package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class TeamAgentServiceTest {
    private JdbcTemplate jdbc;
    private TeamAgentService service;

    @BeforeEach
    void setUp() {
        jdbc = new JdbcTemplate(new DriverManagerDataSource(
                "jdbc:h2:mem:team-agent-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        jdbc.execute("CREATE TABLE app_user (id BIGINT PRIMARY KEY, username VARCHAR(64), enabled BOOLEAN)");
        jdbc.execute("CREATE TABLE team_workspace (id BIGINT PRIMARY KEY, status VARCHAR(16))");
        jdbc.execute("CREATE TABLE team_member (team_id BIGINT, user_id BIGINT, role VARCHAR(16))");
        jdbc.execute("CREATE TABLE team_agent (id BIGINT AUTO_INCREMENT PRIMARY KEY, team_id BIGINT, name VARCHAR(120), description VARCHAR(500), status VARCHAR(16), current_version BIGINT, created_by BIGINT)");
        jdbc.execute("CREATE TABLE team_agent_version (id BIGINT AUTO_INCREMENT PRIMARY KEY, agent_id BIGINT, version_no INT, prompt CLOB, tools_json CLOB, status VARCHAR(16), created_by BIGINT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, revision INT DEFAULT 0, updated_at TIMESTAMP)");
        jdbc.update("INSERT INTO app_user VALUES (1,'owner',TRUE),(2,'member',TRUE),(3,'other',TRUE)");
        jdbc.update("INSERT INTO team_workspace VALUES (10,'active'),(20,'active')");
        jdbc.update("INSERT INTO team_member VALUES (10,1,'owner'),(10,2,'member'),(20,3,'owner')");
        OperationToolService tools = mock(OperationToolService.class);
        when(tools.listTools()).thenReturn(java.util.List.of(
                new OperationToolService.ToolDescriptor("host-health", true, "LOW", false, "HOST_HEALTH"),
                new OperationToolService.ToolDescriptor("docker-containers", true, "LOW", false, "DOCKER_CONTAINERS")));
        service = new TeamAgentService(jdbc, new com.smartops.security.TeamResourceAuthorizer(jdbc), new ObjectMapper(), tools);
    }

    @Test
    void ownerCreatesAndPublishesAgentWhileMemberCanOnlyListIt() {
        var owner = user(1, "owner");
        var agent = service.create(owner, 10, "巡检 Agent", "基础巡检");
        service.saveDraft(owner, agent.id(), "检查服务状态", "[\"host-health\"]");
        var published = service.publish(owner, agent.id());

        assertThat(published.versionNo()).isEqualTo(1);
        assertThat(service.list(user(2, "operator"), 10)).extracting(TeamAgentService.Agent::id).contains(agent.id());

        service.saveDraft(owner, agent.id(), "检查容器状态", "[\"docker-containers\"]");
        var second = service.publish(owner, agent.id());
        assertThat(second.versionNo()).isEqualTo(2);
        assertThat(published.prompt()).isEqualTo("检查服务状态");
    }

    @Test
    void memberCannotCreateOrPublishAndOtherTeamCannotRead() {
        var member = user(2, "operator");
        var agent = service.create(user(1, "owner"), 10, "team agent", "");
        assertThatThrownBy(() -> service.create(member, 10, "越权", ""))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_CAPABILITY_FORBIDDEN");
        assertThatThrownBy(() -> service.list(member, 20))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_ACCESS_FORBIDDEN");
        assertThatThrownBy(() -> service.saveDraft(user(3, "operator"), 20, agent.id(), "prompt", "[]"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_AGENT_NOT_FOUND");
    }

    @Test
    void draftRequiresValidKnownToolIdsAndDetailRestoresDraft() {
        var owner = user(1, "owner");
        var agent = service.create(owner, 10, "team agent", "");
        assertThat(service.catalog(owner, 10)).extracting(OperationToolService.ToolDescriptor::toolId)
                .contains("host-health", "docker-containers");
        assertThatThrownBy(() -> service.catalog(user(2, "operator"), 10))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_CAPABILITY_FORBIDDEN");
        assertThatThrownBy(() -> service.saveDraft(owner, 10, agent.id(), "prompt", "not json"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_AGENT_TOOLS_INVALID");
        assertThatThrownBy(() -> service.saveDraft(owner, 10, agent.id(), "prompt", "[\"unknown-tool\"]"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_AGENT_TOOLS_INVALID");
        service.saveDraft(owner, 10, agent.id(), "inspect only", "[\"host-health\"]");
        assertThat(service.detail(owner, 10, agent.id()).draft().prompt()).isEqualTo("inspect only");
        assertThat(service.detail(owner, 10, agent.id()).draft().toolsJson()).isEqualTo("[\"host-health\"]");
        service.publish(owner, 10, agent.id());
        assertThat(service.detail(owner, 10, agent.id()).currentVersion().versionNo()).isEqualTo(1);
        var memberDetail = service.detail(user(2, "operator"), 10, agent.id());
        assertThat(memberDetail.currentVersion().id()).isEqualTo(service.detail(owner, 10, agent.id()).currentVersion().id());
        assertThat(memberDetail.currentVersion().prompt()).isEmpty();
        assertThat(memberDetail.currentVersion().toolsJson()).isEqualTo("[]");
        assertThat(service.availableTools(user(2, "operator"), 10, agent.id()))
                .extracting(OperationToolService.ToolDescriptor::toolId).containsExactly("host-health");
        assertThatThrownBy(() -> service.availableTools(user(3, "operator"), 20, agent.id()))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_AGENT_NOT_FOUND");
        jdbc.update("UPDATE team_workspace SET status='frozen' WHERE id=10");
        assertThatThrownBy(() -> service.availableTools(user(2, "operator"), 10, agent.id()))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_FROZEN");
    }

    @Test
    void draftSaveRejectsStaleRevisionInsteadOfSilentlyOverwriting() {
        var owner = user(1, "operator");
        var agent = service.create(owner, 10, "concurrent", "note");
        service.saveDraft(owner, 10, agent.id(), "first edit", "[\"host-health\"]");
        Integer revision = service.detail(owner, 10, agent.id()).draft().revision();
        assertThat(revision).isNotNull();

        // 第一路基于 revision 保存：成功，revision 前进
        service.saveDraft(owner, 10, agent.id(), "second edit", "[\"host-health\"]", revision);
        Integer afterFirst = service.detail(owner, 10, agent.id()).draft().revision();
        assertThat(afterFirst).isEqualTo(revision + 1);

        // 第二路仍拿旧 revision 保存（模拟另一个人基于旧内容编辑）：必须被拒绝，而不是静默覆盖
        assertThatThrownBy(() -> service.saveDraft(owner, 10, agent.id(),
                "stale overwrite", "[\"host-health\"]", revision))
                .isInstanceOf(BusinessException.class).satisfies(failure ->
                        assertThat(((BusinessException) failure).getCode()).isEqualTo(409));
        // 关键断言：内容仍是第一路的，没有被静默覆盖
        assertThat(service.detail(owner, 10, agent.id()).draft().prompt()).isEqualTo("second edit");

        // 不带 revision（旧前端）仍可保存，保持兼容
        service.saveDraft(owner, 10, agent.id(), "legacy save", "[\"host-health\"]");
        assertThat(service.detail(owner, 10, agent.id()).draft().prompt()).isEqualTo("legacy save");
    }

    @Test
    void staleRevisionOnMissingDraftIsRejected() {
        var owner = user(1, "operator");
        var agent = service.create(owner, 10, "no-draft", "note");
        // 客户端声称在编辑 revision>0 的草稿，但草稿不存在 —— 说明它读到的是过期状态
        assertThatThrownBy(() -> service.saveDraft(owner, 10, agent.id(), "x", "[\"host-health\"]", 3))
                .isInstanceOf(BusinessException.class).satisfies(failure ->
                        assertThat(((BusinessException) failure).getCode()).isEqualTo(409));
    }

    private SessionUser user(long id, String role) { return new SessionUser(id, "u" + id, "operator", "user", false, 0); }
}
