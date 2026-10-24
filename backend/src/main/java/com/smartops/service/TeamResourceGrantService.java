package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class TeamResourceGrantService {
    private final JdbcTemplate jdbc;
    private final TeamResourceAuthorizer authorizer;
    public TeamResourceGrantService(JdbcTemplate jdbc, TeamResourceAuthorizer authorizer) { this.jdbc = jdbc; this.authorizer = authorizer; }

    public List<Grant> list(SessionUser actor, long teamId, String resourceType, String resourceId) {
        authorizer.requireMember(actor, teamId, "view");
        return jdbc.query("SELECT g.team_id,g.resource_type,g.resource_id,g.user_id,u.username,g.capability,g.granted_by,g.created_at FROM team_resource_grant g JOIN app_user u ON u.id=g.user_id WHERE g.team_id=? AND g.resource_type=? AND g.resource_id=? ORDER BY g.user_id,g.capability",
                (row, ignored) -> new Grant(row.getLong("team_id"), row.getString("resource_type"), row.getString("resource_id"), row.getLong("user_id"), row.getString("username"), row.getString("capability"), row.getLong("granted_by"), row.getTimestamp("created_at").toInstant().toString()), teamId, resourceType, resourceId);
    }

    @Transactional
    public void grant(SessionUser actor, long teamId, String resourceType, String resourceId, long userId, String capability) {
        var permission = authorizer.requireMember(actor, teamId, "manage");
        if (!("owner".equals(permission.role()) || "admin".equals(permission.role()))) throw new BusinessException(403, "需要团队管理权限");
        if (!List.of("agent", "knowledge", "connection").contains(resourceType) || !List.of("view", "edit", "run", "publish", "approve").contains(capability) || resourceId == null || resourceId.isBlank() || resourceId.length() > 128) throw new BusinessException(400, "资源授权参数无效");
        if (jdbc.queryForList("SELECT user_id FROM team_member WHERE team_id=? AND user_id=?", Long.class, teamId, userId).isEmpty()) throw new BusinessException(404, "目标用户不是团队成员");
        jdbc.update("INSERT INTO team_resource_grant(team_id,resource_type,resource_id,user_id,capability,granted_by) VALUES(?,?,?,?,?,?) ON DUPLICATE KEY UPDATE granted_by=VALUES(granted_by)", teamId, resourceType, resourceId, userId, capability, actor.id());
    }

    @Transactional
    public void revoke(SessionUser actor, long teamId, String resourceType, String resourceId, long userId, String capability) {
        authorizer.requireMember(actor, teamId, "manage");
        jdbc.update("DELETE FROM team_resource_grant WHERE team_id=? AND resource_type=? AND resource_id=? AND user_id=? AND capability=?", teamId, resourceType, resourceId, userId, capability);
    }
    public record Grant(long teamId, String resourceType, String resourceId, long userId, String username, String capability, long grantedBy, String createdAt) {}
}
