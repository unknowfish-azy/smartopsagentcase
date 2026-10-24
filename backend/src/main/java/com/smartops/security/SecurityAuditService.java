package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

@Service
public class SecurityAuditService {
    private static final Set<String> ACTIONS = Set.of("LOGIN", "LOGOUT", "CREATE_USER", "UPDATE_USER", "RESET_PASSWORD", "CHANGE_PASSWORD", "PROFILE_UPDATE", "REVOKE_SESSION", "REGISTER", "REGISTRATION_POLICY", "ADMIN_VERIFY", "HUMAN_VERIFY", "MFA_ENABLE", "MFA_DISABLE", "MFA_VERIFY", "MFA_RECOVERY_ROTATE", "MFA_RECOVERY_USE", "TEAM_CREATE", "TEAM_UPDATE", "TEAM_INVITE", "TEAM_INVITE_RESPOND", "TEAM_INVITE_CANCEL", "TEAM_MEMBER_ROLE", "TEAM_MEMBER_REMOVE", "TEAM_STATUS", "TEAM_AGENT_RUN_CREATE", "TEAM_AGENT_RUN_APPROVE", "TEAM_AGENT_RUN_EXECUTE", "TEAM_AGENT_RUN_FINISH", "CHAT_CONVERSATION_CREATE", "CHAT_CONVERSATION_DELETE", "CHAT_ATTACHMENT_UPLOAD", "DEPT_CREATE", "DEPT_UPDATE", "DEPT_DELETE", "DEPT_STATUS", "POST_CREATE", "POST_UPDATE", "POST_DELETE", "POST_STATUS", "ROLE_CREATE", "ROLE_UPDATE", "ROLE_DELETE", "ROLE_STATUS", "ROLE_MENU_GRANT", "MENU_CREATE", "MENU_UPDATE", "MENU_DELETE", "MENU_STATUS", "DICT_TYPE_CREATE", "DICT_TYPE_UPDATE", "DICT_TYPE_DELETE", "DICT_TYPE_STATUS", "DICT_DATA_CREATE", "DICT_DATA_UPDATE", "DICT_DATA_DELETE", "DICT_DATA_STATUS", "NOTICE_CREATE", "NOTICE_UPDATE", "NOTICE_DELETE", "NOTICE_PUBLISH");
    private static final Set<String> OUTCOMES = Set.of("SUCCESS", "FAILURE", "DENIED");
    private final JdbcTemplate jdbc;

    public SecurityAuditService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public void record(SessionUser actor, String action, String targetId, String outcome) {
        insert(actor == null ? null : actor.id(), actor == null ? "anonymous" : actor.username(), action, targetId, outcome);
    }

    public void failedLogin(String username, String outcome) { insert(null, username, "LOGIN", null, outcome); }

    private void insert(Long actorId, String username, String action, String targetId, String outcome) {
        String safeName = username == null ? "anonymous" : username.replaceAll("[\\r\\n\\t]", " ");
        jdbc.update("INSERT INTO security_audit_event(actor_id,actor_username,action,target_id,outcome) VALUES(?,?,?,?,?)",
                actorId, safeName.substring(0, Math.min(64, safeName.length())), action, targetId, outcome);
    }

    public AuditPage list(String action, String outcome, String query, int page, int pageSize) {
        validatePage(page, pageSize);
        if (action != null && !action.isBlank() && !ACTIONS.contains(action)) throw new BusinessException(400, "审计事件类型无效");
        if (outcome != null && !outcome.isBlank() && !OUTCOMES.contains(outcome)) throw new BusinessException(400, "审计结果无效");
        StringBuilder where = new StringBuilder(" WHERE 1=1");
        var values = new ArrayList<Object>();
        if (action != null && !action.isBlank()) { where.append(" AND action=?"); values.add(action); }
        if (outcome != null && !outcome.isBlank()) { where.append(" AND outcome=?"); values.add(outcome); }
        if (query != null && !query.isBlank()) {
            if (query.length() > 64) throw new BusinessException(400, "搜索内容不能超过 64 个字符");
            where.append(" AND LOCATE(LOWER(?),LOWER(actor_username))>0"); values.add(query.trim());
        }
        long total = jdbc.queryForObject("SELECT COUNT(*) FROM security_audit_event" + where, Long.class, values.toArray());
        values.add(pageSize); values.add((page - 1L) * pageSize);
        var items = jdbc.query("SELECT id,actor_id,actor_username,action,target_id,outcome,created_at FROM security_audit_event" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                (result, row) -> new AuditEntry(result.getLong("id"), result.getObject("actor_id", Long.class), result.getString("actor_username"), result.getString("action"), result.getString("target_id"), result.getString("outcome"), result.getTimestamp("created_at").toInstant().toString()), values.toArray());
        return new AuditPage(items, total, page, pageSize);
    }

    public static void validatePage(int page, int pageSize) {
        if (page < 1 || page > 1000000 || pageSize < 1 || pageSize > 100) throw new BusinessException(400, "分页参数无效，每页需为 1–100 条");
    }

    public record AuditEntry(Long id, Long actorId, String actorUsername, String action, String targetId, String outcome, String createdAt) {}
    public record AuditPage(List<AuditEntry> items, long total, int page, int pageSize) {}
}
