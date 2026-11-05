package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class TeamResourceAuthorizerTest {
    private JdbcTemplate jdbc;
    private TeamResourceAuthorizer authorizer;

    @BeforeEach
    void setUp() {
        jdbc = new JdbcTemplate(new DriverManagerDataSource(
                "jdbc:h2:mem:team-authorizer-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        jdbc.execute("CREATE TABLE app_user (id BIGINT PRIMARY KEY, username VARCHAR(64), enabled BOOLEAN)");
        jdbc.execute("CREATE TABLE team_workspace (id BIGINT PRIMARY KEY, status VARCHAR(16), owner_id BIGINT)");
        jdbc.execute("CREATE TABLE team_member (team_id BIGINT, user_id BIGINT, role VARCHAR(16))");
        jdbc.execute("CREATE TABLE team_member_capability (team_id BIGINT, user_id BIGINT, capability VARCHAR(32))");
        jdbc.execute("CREATE TABLE team_resource_grant (team_id BIGINT, resource_type VARCHAR(32), resource_id VARCHAR(128), user_id BIGINT, capability VARCHAR(32), granted_by BIGINT)");
        jdbc.update("INSERT INTO app_user VALUES (1,'owner',TRUE),(2,'member',TRUE),(3,'viewer',TRUE),(4,'other',TRUE),(5,'specialist',TRUE)");
        jdbc.update("INSERT INTO team_workspace VALUES (10,'active',1),(20,'active',4),(30,'frozen',1)");
        jdbc.update("INSERT INTO team_member VALUES (10,1,'owner'),(10,2,'member'),(10,3,'viewer'),(10,5,'specialist'),(20,4,'owner'),(30,1,'owner')");
        authorizer = new TeamResourceAuthorizer(jdbc);
    }

    @Test
    void memberCanRunOnlyInsideTheirActiveTeam() {
        var permission = authorizer.requireMember(user(2), 10, "run");

        assertThat(permission.teamId()).isEqualTo(10L);
        assertThat(permission.role()).isEqualTo("member");
    }

    @Test
    void viewerCannotRunAndMemberCannotCrossTeamBoundary() {
        assertThatThrownBy(() -> authorizer.requireMember(user(3), 10, "run"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_CAPABILITY_FORBIDDEN");
        assertThatThrownBy(() -> authorizer.requireMember(user(2), 20, "view"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_ACCESS_FORBIDDEN");
    }

    @Test
    void frozenTeamRejectsMutationsButAllowsView() {
        assertThat(authorizer.requireMember(user(1), 30, "view").teamId()).isEqualTo(30L);
        assertThatThrownBy(() -> authorizer.requireMember(user(1), 30, "run"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_FROZEN");
    }

    @Test
    void resourceGrantAddsScopedCapabilityAndRevokeTakesEffectImmediately() {
        assertThatThrownBy(() -> authorizer.requireResource(user(5), 10, "agent", "42", "edit"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_CAPABILITY_FORBIDDEN");
        jdbc.update("INSERT INTO team_resource_grant VALUES (10,'agent','42',5,'edit',1)");
        assertThat(authorizer.requireResource(user(5), 10, "agent", "42", "edit").role()).isEqualTo("specialist");
        jdbc.update("DELETE FROM team_resource_grant WHERE team_id=10 AND resource_type='agent' AND resource_id='42' AND user_id=5 AND capability='edit'");
        assertThatThrownBy(() -> authorizer.requireResource(user(5), 10, "agent", "42", "edit"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_CAPABILITY_FORBIDDEN");
    }

    @Test
    void adminPortalSessionDoesNotBypassTeamMembership() {
        var admin = new SessionUser(9L, "admin9", "admin", "admin", false, 0);
        assertThatThrownBy(() -> authorizer.requireMember(admin, 10, "view"))
                .isInstanceOf(BusinessException.class).hasMessage("TEAM_ACCESS_FORBIDDEN");
    }

    private SessionUser user(long id) { return new SessionUser(id, "u" + id, "operator", "user", false, 0); }
}
