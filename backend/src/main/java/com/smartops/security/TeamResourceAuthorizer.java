package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.Set;

@Service
public class TeamResourceAuthorizer {
    private static final Set<String> CAPABILITIES = Set.of("view", "run", "approve", "manage");
    private static final Set<String> RESOURCE_TYPES = Set.of("agent", "knowledge", "connection");
    private static final Set<String> RESOURCE_CAPABILITIES = Set.of("view", "edit", "run", "publish", "approve");
    private final JdbcTemplate jdbc;

    public TeamResourceAuthorizer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public TeamPermission requireMember(SessionUser actor, long teamId, String capability) {
        if (actor == null || !CAPABILITIES.contains(capability)) {
            throw new BusinessException(403, "TEAM_ACCESS_FORBIDDEN");
        }
        TeamPermission permission = requireTeamMember(actor, teamId);
        if (!"view".equals(capability) && "frozen".equals(permission.status())) {
            throw new BusinessException(403, "TEAM_FROZEN");
        }
        if (!allowed(permission.role(), capability, teamId, actor.id())) throw new BusinessException(403, "TEAM_CAPABILITY_FORBIDDEN");
        return permission;
    }

    public TeamPermission requireTeamMember(SessionUser actor, long teamId) {
        if (actor == null) throw new BusinessException(403, "TEAM_ACCESS_FORBIDDEN");
        var teams = jdbc.query("SELECT t.status,m.role,u.enabled FROM team_workspace t "
                        + "JOIN team_member m ON m.team_id=t.id AND m.user_id=? "
                        + "JOIN app_user u ON u.id=m.user_id WHERE t.id=?",
                (result, row) -> new TeamPermission(teamId, result.getString("status"), result.getString("role"), result.getBoolean("enabled")),
                actor.id(), teamId);
        if (teams.isEmpty()) {
            // 管理员入口不授予团队成员权限：管理端走 /api/admin/teams 的独立授权路径。
            throw new BusinessException(403, "TEAM_ACCESS_FORBIDDEN");
        }
        TeamPermission permission = teams.get(0);
        if (!permission.enabled()) throw new BusinessException(403, "TEAM_ACCESS_FORBIDDEN");
        return permission;
    }

    public TeamPermission requireResource(SessionUser actor, long teamId, String capability) {
        return requireMember(actor, teamId, capability);
    }

    public TeamPermission requireResource(SessionUser actor, long teamId, String resourceType, String resourceId, String capability) {
        if (!RESOURCE_TYPES.contains(resourceType) || resourceId == null || resourceId.isBlank()
                || !RESOURCE_CAPABILITIES.contains(capability)) {
            throw new BusinessException(403, "TEAM_ACCESS_FORBIDDEN");
        }
        TeamPermission permission = requireTeamMember(actor, teamId);
        if (!"view".equals(capability) && "frozen".equals(permission.status())) {
            throw new BusinessException(403, "TEAM_FROZEN");
        }
        String teamCapability = switch (capability) {
            case "edit", "publish" -> "manage";
            default -> capability;
        };
        if (allowed(permission.role(), teamCapability, teamId, actor.id())) return permission;
        boolean granted = !jdbc.queryForList("SELECT user_id FROM team_resource_grant WHERE team_id=? AND resource_type=? AND resource_id=? AND user_id=? AND capability=?",
                teamId, resourceType, resourceId, actor.id(), capability).isEmpty();
        if (!granted) throw new BusinessException(403, "TEAM_CAPABILITY_FORBIDDEN");
        return permission;
    }

    private boolean allowed(String role, String capability, long teamId, long userId) {
        if ("specialist".equals(role)) {
            return !jdbc.queryForList("SELECT capability FROM team_member_capability WHERE team_id=? AND user_id=? AND capability=?", teamId, userId, capability).isEmpty();
        }
        return switch (capability) {
            case "view" -> Set.of("owner", "admin", "member", "viewer", "root").contains(role);
            case "run" -> Set.of("owner", "admin", "member", "root").contains(role);
            case "approve", "manage" -> Set.of("owner", "admin", "root").contains(role);
            default -> false;
        };
    }

    public record TeamPermission(long teamId, String status, String role, boolean enabled) {}
}
