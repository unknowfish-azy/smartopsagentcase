package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class TeamResourceShareService {
    private static final String KNOWLEDGE = "knowledge";
    private final JdbcTemplate jdbc;
    private final TeamResourceAuthorizer authorizer;
    private final TeamActivityService activity;
    private final SecurityAuditService audit;

    public TeamResourceShareService(JdbcTemplate jdbc, TeamResourceAuthorizer authorizer, TeamActivityService activity, SecurityAuditService audit) {
        this.jdbc = jdbc;
        this.authorizer = authorizer;
        this.activity = activity;
        this.audit = audit;
    }

    public List<SharedResource> list(SessionUser actor, long teamId, String resourceType) {
        authorizer.requireMember(actor, teamId, "view");
        String type = type(resourceType);
        return jdbc.query("SELECT s.id,s.team_id,s.resource_type,s.resource_id,l.name,l.description,l.status,l.user_id,u.username,s.created_at,"
                        + "(SELECT COUNT(*) FROM personal_knowledge_entry e WHERE e.library_id=l.id) AS entry_count "
                        + "FROM team_resource_share s JOIN personal_knowledge_library l ON l.id=s.resource_id JOIN app_user u ON u.id=l.user_id "
                        + "WHERE s.team_id=? AND s.resource_type=? ORDER BY s.id DESC",
                (row, ignored) -> new SharedResource(row.getLong("id"), row.getLong("team_id"), row.getString("resource_type"), row.getLong("resource_id"),
                        row.getString("name"), row.getString("description"), row.getString("status"), row.getLong("user_id"), row.getString("username"),
                        row.getInt("entry_count"), row.getTimestamp("created_at").toInstant().toString()), teamId, type);
    }

    public Library library(SessionUser actor, long teamId, long libraryId) {
        authorizer.requireMember(actor, teamId, "view");
        requireShared(teamId, libraryId);
        var rows = jdbc.query("SELECT l.id,l.user_id,l.name,l.description,l.status,l.updated_at,u.username FROM personal_knowledge_library l JOIN app_user u ON u.id=l.user_id WHERE l.id=? AND l.status='ACTIVE'",
                (row, ignored) -> new Library(row.getLong("id"), row.getLong("user_id"), row.getString("username"), row.getString("name"),
                        row.getString("description"), row.getString("status"), row.getTimestamp("updated_at").toInstant().toString()), libraryId);
        if (rows.isEmpty()) throw new BusinessException(404, "共享知识库不存在或已归档");
        return rows.get(0);
    }

    public EntryPage entries(SessionUser actor, long teamId, long libraryId, String query, int page, int pageSize) {
        authorizer.requireMember(actor, teamId, "view");
        requireShared(teamId, libraryId);
        int safePage = Math.max(1, page);
        int safeSize = Math.max(1, Math.min(50, pageSize));
        boolean filtered = query != null && !query.isBlank();
        String value = filtered ? "%" + query.trim().toLowerCase() + "%" : null;
        String where = filtered ? " WHERE library_id=? AND (LOWER(title) LIKE ? OR LOWER(summary) LIKE ?)" : " WHERE library_id=?";
        Object[] countArgs = filtered ? new Object[]{libraryId, value, value} : new Object[]{libraryId};
        long total = jdbc.queryForObject("SELECT COUNT(*) FROM personal_knowledge_entry" + where, Long.class, countArgs);
        Object[] args = filtered
                ? new Object[]{libraryId, value, value, safeSize, (safePage - 1) * safeSize}
                : new Object[]{libraryId, safeSize, (safePage - 1) * safeSize};
        List<Entry> items = jdbc.query("SELECT id,title,summary,content_markdown,source_type,verification_status,version,updated_at FROM personal_knowledge_entry" + where + " ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?",
                (row, ignored) -> new Entry(row.getLong("id"), row.getString("title"), row.getString("summary"), row.getString("content_markdown"),
                        row.getString("source_type"), row.getString("verification_status"), row.getInt("version"), row.getTimestamp("updated_at").toInstant().toString()), args);
        return new EntryPage(items, total, safePage, safeSize);
    }

    @Transactional
    public void share(SessionUser actor, long teamId, String resourceType, long resourceId) {
        authorizer.requireTeamMember(actor, teamId);
        String type = type(resourceType);
        String status = jdbc.queryForObject("SELECT status FROM team_workspace WHERE id=?", String.class, teamId);
        if ("frozen".equals(status)) throw new BusinessException(403, "团队已冻结，暂不能共享资源");
        var owners = jdbc.queryForList("SELECT user_id FROM personal_knowledge_library WHERE id=? AND status='ACTIVE'", Long.class, resourceId);
        if (owners.isEmpty()) throw new BusinessException(404, "知识库不存在或已归档");
        if (owners.get(0).longValue() != actor.id()) throw new BusinessException(403, "只能共享自己创建的知识库");
        jdbc.update("INSERT INTO team_resource_share(team_id,resource_type,resource_id,shared_by) VALUES(?,?,?,?) ON DUPLICATE KEY UPDATE shared_by=VALUES(shared_by)",
                teamId, type, resourceId, actor.id());
        activity.record(actor, teamId, "TEAM_RESOURCE_SHARE", type + ":" + resourceId);
        audit.record(actor, "TEAM_RESOURCE_SHARE", teamId + ":" + type + ":" + resourceId, "SUCCESS");
    }

    @Transactional
    public void unshare(SessionUser actor, long teamId, String resourceType, long resourceId) {
        var permission = authorizer.requireMember(actor, teamId, "view");
        String type = type(resourceType);
        var shares = jdbc.queryForList("SELECT shared_by FROM team_resource_share WHERE team_id=? AND resource_type=? AND resource_id=?", Long.class, teamId, type, resourceId);
        if (shares.isEmpty()) throw new BusinessException(404, "共享记录不存在");
        boolean manager = List.of("owner", "admin", "root").contains(permission.role());
        var owners = jdbc.queryForList("SELECT user_id FROM personal_knowledge_library WHERE id=?", Long.class, resourceId);
        boolean owner = !owners.isEmpty() && owners.get(0).longValue() == actor.id();
        if (!manager && !owner && shares.get(0).longValue() != actor.id()) throw new BusinessException(403, "只有共享人、知识库所有者或团队管理员可以取消共享");
        jdbc.update("DELETE FROM team_resource_share WHERE team_id=? AND resource_type=? AND resource_id=?", teamId, type, resourceId);
        activity.record(actor, teamId, "TEAM_RESOURCE_UNSHARE", type + ":" + resourceId);
        audit.record(actor, "TEAM_RESOURCE_UNSHARE", teamId + ":" + type + ":" + resourceId, "SUCCESS");
    }

    private String type(String resourceType) {
        if (!KNOWLEDGE.equals(resourceType)) throw new BusinessException(400, "暂不支持该资源类型");
        return resourceType;
    }

    private void requireShared(long teamId, long libraryId) {
        if (jdbc.queryForList("SELECT id FROM team_resource_share WHERE team_id=? AND resource_type='knowledge' AND resource_id=?", Long.class, teamId, libraryId).isEmpty())
            throw new BusinessException(404, "该知识库未共享到当前团队");
    }

    public record SharedResource(long id, long teamId, String resourceType, long resourceId, String name, String description, String status,
                                 long ownerId, String ownerName, int entryCount, String sharedAt) {}
    public record Library(long id, long ownerId, String ownerName, String name, String description, String status, String updatedAt) {}
    public record Entry(long id, String title, String summary, String contentMarkdown, String sourceType, String verificationStatus, int version, String updatedAt) {}
    public record EntryPage(List<Entry> items, long total, int page, int pageSize) {}
}
