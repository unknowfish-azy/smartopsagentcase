package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

@Service
public class SecurityAuditService {
    private static final Set<String> ACTIONS = Set.of("LOGIN", "LOGOUT", "CREATE_USER", "UPDATE_USER", "RESET_PASSWORD", "CHANGE_PASSWORD", "PROFILE_UPDATE", "REVOKE_SESSION", "REGISTER", "REGISTRATION_POLICY", "ADMIN_VERIFY", "HUMAN_VERIFY", "MFA_ENABLE", "MFA_DISABLE", "MFA_VERIFY", "MFA_RECOVERY_ROTATE", "MFA_RECOVERY_USE", "TEAM_CREATE", "TEAM_UPDATE", "TEAM_INVITE", "TEAM_INVITE_RESPOND", "TEAM_INVITE_CANCEL", "TEAM_INVITE_LINK_CREATE", "TEAM_INVITE_LINK_JOIN", "TEAM_INVITE_LINK_REVOKE", "TEAM_MEMBER_ROLE", "TEAM_MEMBER_REMOVE", "TEAM_STATUS", "TEAM_AGENT_RUN_CREATE", "TEAM_AGENT_RUN_APPROVE", "TEAM_AGENT_RUN_EXECUTE", "TEAM_AGENT_RUN_FINISH", "CHAT_CONVERSATION_CREATE", "CHAT_CONVERSATION_DELETE", "CHAT_ATTACHMENT_UPLOAD", "DEPT_CREATE", "DEPT_UPDATE", "DEPT_DELETE", "DEPT_STATUS", "POST_CREATE", "POST_UPDATE", "POST_DELETE", "POST_STATUS", "ROLE_CREATE", "ROLE_UPDATE", "ROLE_DELETE", "ROLE_STATUS", "ROLE_MENU_GRANT", "MENU_CREATE", "MENU_UPDATE", "MENU_DELETE", "MENU_STATUS", "DICT_TYPE_CREATE", "DICT_TYPE_UPDATE", "DICT_TYPE_DELETE", "DICT_TYPE_STATUS", "DICT_DATA_CREATE", "DICT_DATA_UPDATE", "DICT_DATA_DELETE", "DICT_DATA_STATUS", "NOTICE_CREATE", "NOTICE_UPDATE", "NOTICE_DELETE", "NOTICE_PUBLISH", "PLATFORM_ADMIN_APPOINT", "PLATFORM_ADMIN_REVOKE", "PLATFORM_ROOT_TRANSFER");
    private static final Set<String> OUTCOMES = Set.of("SUCCESS", "FAILURE", "DENIED");
    private final JdbcTemplate jdbc;

    public SecurityAuditService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public void record(SessionUser actor, String action, String targetId, String outcome) {
        record(actor, action, targetId, outcome, null);
    }

    /** 结果与依据分开：outcome 只允许三值，审批依据等上下文写入 detail 列。 */
    public void record(SessionUser actor, String action, String targetId, String outcome, String detail) {
        insert(actor == null ? null : actor.id(), actor == null ? "anonymous" : actor.username(), action, targetId, outcome, detail);
    }

    public void failedLogin(String username, String outcome) { insert(null, username, "LOGIN", null, outcome, null); }

    private void insert(Long actorId, String username, String action, String targetId, String outcome, String detail) {
        String safeName = username == null ? "anonymous" : username.replaceAll("[\\r\\n\\t]", " ");
        String safeDetail = detail == null ? null : detail.replaceAll("[\\r\\n\\t]", " ").trim();
        if (safeDetail != null && safeDetail.length() > 500) safeDetail = safeDetail.substring(0, 500);
        jdbc.update("INSERT INTO security_audit_event(actor_id,actor_username,action,target_id,outcome,detail) VALUES(?,?,?,?,?,?)",
                actorId, safeName.substring(0, Math.min(64, safeName.length())), action, targetId, outcome, safeDetail);
    }

    public AuditPage list(String action, String outcome, String query, int page, int pageSize) {
        return list(action, outcome, query, null, null, null, page, pageSize);
    }

    public AuditPage list(String action, String outcome, String query, String targetId, String from, String to, int page, int pageSize) {
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
        if (targetId != null && !targetId.isBlank()) {
            if (targetId.length() > 64) throw new BusinessException(400, "目标标识不能超过 64 个字符");
            where.append(" AND target_id=?"); values.add(targetId.trim());
        }
        // 时间范围按服务器本地时区解释，[起始日 00:00, 结束日次日 00:00) 的半开区间，避免跨日重复。
        if (from != null && !from.isBlank()) { where.append(" AND created_at>=?"); values.add(boundary(from)); }
        if (to != null && !to.isBlank()) { where.append(" AND created_at<?"); values.add(endBoundary(to)); }
        long total = jdbc.queryForObject("SELECT COUNT(*) FROM security_audit_event" + where, Long.class, values.toArray());
        values.add(pageSize); values.add((page - 1L) * pageSize);
        var items = jdbc.query("SELECT id,actor_id,actor_username,action,target_id,outcome,detail,created_at FROM security_audit_event" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                (result, row) -> new AuditEntry(result.getLong("id"), result.getObject("actor_id", Long.class), result.getString("actor_username"), result.getString("action"), result.getString("target_id"), result.getString("outcome"), result.getString("detail"), result.getTimestamp("created_at").toInstant().toString()), values.toArray());
        return new AuditPage(items, total, page, pageSize);
    }

    /** 单条审计详情：与列表同一作用域（控制器已校验 admin.audit），额外补 ip 列。 */
    public AuditDetail detail(long id) {
        var rows = jdbc.query("SELECT id,actor_id,actor_username,action,target_id,outcome,detail,ip,created_at FROM security_audit_event WHERE id=?",
                (result, row) -> new AuditDetail(result.getLong("id"), result.getObject("actor_id", Long.class), result.getString("actor_username"), result.getString("action"),
                        result.getString("target_id"), result.getString("outcome"), result.getString("detail"), result.getString("ip"), result.getTimestamp("created_at").toInstant().toString()), id);
        if (rows.isEmpty()) throw new BusinessException(404, "审计记录不存在");
        return rows.get(0);
    }

    private static final java.time.format.DateTimeFormatter DATE = java.time.format.DateTimeFormatter.ISO_LOCAL_DATE;

    private static java.sql.Timestamp boundary(String date) {
        try { return java.sql.Timestamp.valueOf(java.time.LocalDate.parse(date, DATE).atStartOfDay()); }
        catch (java.time.format.DateTimeParseException invalid) { throw new BusinessException(400, "日期格式无效，应为 YYYY-MM-DD"); }
    }

    private static java.sql.Timestamp endBoundary(String date) {
        try { return java.sql.Timestamp.valueOf(java.time.LocalDate.parse(date, DATE).plusDays(1).atStartOfDay()); }
        catch (java.time.format.DateTimeParseException invalid) { throw new BusinessException(400, "日期格式无效，应为 YYYY-MM-DD"); }
    }

    public static void validatePage(int page, int pageSize) {
        if (page < 1 || page > 1000000 || pageSize < 1 || pageSize > 100) throw new BusinessException(400, "分页参数无效，每页需为 1–100 条");
    }

    public record AuditEntry(Long id, Long actorId, String actorUsername, String action, String targetId, String outcome, String detail, String createdAt) {}
    public record AuditDetail(long id, Long actorId, String actorUsername, String action, String targetId, String outcome, String detail, String ip, String createdAt) {}
    public record AuditPage(List<AuditEntry> items, long total, int page, int pageSize) {}
}
