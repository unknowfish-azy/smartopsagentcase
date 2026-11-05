package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Isolation;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;

@Service
public class TeamWorkspaceService {
    private final JdbcTemplate jdbc;
    private final SecurityAuditService audit;
    private final UserAccountService accounts;
    private final TeamActivityService activity;
    private final TeamNotificationService notifications;

    public TeamWorkspaceService(JdbcTemplate jdbc, SecurityAuditService audit, UserAccountService accounts, TeamActivityService activity, TeamNotificationService notifications) { this.jdbc = jdbc; this.audit = audit; this.accounts = accounts; this.activity = activity; this.notifications = notifications; }

    public Page<Team> list(SessionUser actor, int page, int pageSize) {
        SecurityAuditService.validatePage(page, pageSize);
        long total = count("SELECT COUNT(*) FROM team_member WHERE user_id=?", actor.id());
        var items = jdbc.query("SELECT t.*,m.role,u.username AS owner_name,(SELECT COUNT(*) FROM team_member c WHERE c.team_id=t.id) AS member_count FROM team_workspace t JOIN team_member m ON m.team_id=t.id JOIN app_user u ON u.id=t.owner_id WHERE m.user_id=? ORDER BY t.id DESC LIMIT ? OFFSET ?",
                (result, row) -> team(result), actor.id(), pageSize, (page - 1L) * pageSize);
        return new Page<>(items, total, page, pageSize);
    }

    @Transactional
    public Team create(SessionUser actor, String name, String description) {
        jdbc.queryForObject("SELECT id FROM app_user WHERE id=? FOR UPDATE", Long.class, actor.id());
        if (count("SELECT COUNT(*) FROM team_workspace WHERE owner_id=?", actor.id()) >= 10) throw new BusinessException(409, "每个账号最多创建 10 个团队");
        var key = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("INSERT INTO team_workspace(name,description,owner_id) VALUES(?,?,?)", new String[]{"id"});
            statement.setString(1, text(name, 80)); statement.setString(2, description(description)); statement.setLong(3, actor.id());
            return statement;
        }, key);
        long id = key.getKey().longValue();
        jdbc.update("INSERT INTO team_member(team_id,user_id,role) VALUES(?,?,'owner')", id, actor.id());
        audit.record(actor, "TEAM_CREATE", String.valueOf(id), "SUCCESS");
        return detail(actor, id).team();
    }

    public Detail detail(SessionUser actor, long id) {
        String role = requireMember(id, actor.id());
        Team team = teamById(id, role);
        var invitations = manages(role) ? invitationsForTeam(id) : List.<Invitation>of();
        return new Detail(team, members(id), invitations);
    }

    @Transactional
    public void update(SessionUser actor, long id, String name, String description) {
        lock(id); requireManager(id, actor.id()); requireActive(id);
        jdbc.update("UPDATE team_workspace SET name=?,description=? WHERE id=?", text(name, 80), description(description), id);
        audit.record(actor, "TEAM_UPDATE", String.valueOf(id), "SUCCESS");
    }

    @Transactional
    public void invite(SessionUser actor, long id, String username, String role) {
        lock(id);
        String actorRole = requireManager(id, actor.id()); requireActive(id);
        assignable(actorRole, role);
        var users = jdbc.queryForList("SELECT id FROM app_user WHERE username=? AND enabled=TRUE", Long.class, text(username, 64));
        if (users.isEmpty()) throw new BusinessException(400, "无法邀请该账号，请核对用户名及账号状态");
        long target = users.get(0);
        if (role(id, target) != null) throw new BusinessException(409, "该账号已是团队成员");
        if (count("SELECT COUNT(*) FROM team_member WHERE team_id=?", id) >= 100) throw new BusinessException(409, "团队最多 100 名成员");
        var existing = jdbc.queryForList("SELECT id FROM team_invitation WHERE team_id=? AND invitee_id=? AND status='pending' AND expires_at>?", Long.class, id, target, Timestamp.from(Instant.now()));
        if (!existing.isEmpty()) throw new BusinessException(409, "邀请已发送，请等待对方处理或先撤销");
        if (count("SELECT COUNT(*) FROM team_invitation WHERE team_id=? AND status='pending' AND expires_at>?", id, Timestamp.from(Instant.now())) >= 50) throw new BusinessException(409, "待处理邀请已达上限");
        jdbc.update("DELETE FROM team_invitation WHERE team_id=? AND invitee_id=?", id, target);
        jdbc.update("INSERT INTO team_invitation(team_id,invitee_id,invited_by,role,expires_at) VALUES(?,?,?,?,?)", id, target, actor.id(), role, Timestamp.from(Instant.now().plus(7, ChronoUnit.DAYS)));
        notifications.notifyUser(target, id, "TEAM_INVITATION", Long.toString(id), "你收到一条新的团队邀请");
        audit.record(actor, "TEAM_INVITE", id + ":user:" + target + ":" + role, "SUCCESS");
    }

    public Page<Invitation> inbox(SessionUser actor, int page, int pageSize) {
        SecurityAuditService.validatePage(page, pageSize);
        var now = Timestamp.from(Instant.now());
        String where = " WHERE i.invitee_id=? AND i.status='pending' AND i.expires_at>?";
        long total = count("SELECT COUNT(*) FROM team_invitation i" + where, actor.id(), now);
        var items = jdbc.query(invitationSelect() + where + " ORDER BY i.id DESC LIMIT ? OFFSET ?", (result, row) -> invitation(result), actor.id(), now, pageSize, (page - 1L) * pageSize);
        return new Page<>(items, total, page, pageSize);
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void respond(SessionUser actor, long invitationId, boolean accept) {
        var found = jdbc.queryForList("SELECT team_id FROM team_invitation WHERE id=? AND invitee_id=?", Long.class, invitationId, actor.id());
        if (found.isEmpty()) throw missing();
        long id = found.get(0); lock(id);
        var invitations = jdbc.query("SELECT invited_by,role FROM team_invitation WHERE id=? AND invitee_id=? AND status='pending' AND expires_at>?",
                (result, row) -> new Pending(result.getLong("invited_by"), result.getString("role")), invitationId, actor.id(), Timestamp.from(Instant.now()));
        if (invitations.isEmpty()) throw new BusinessException(409, "邀请已处理、撤销或过期");
        var invitation = invitations.get(0);
        if (accept) {
            requireActive(id);
            String inviterRole = role(id, invitation.inviter());
            if (!manages(inviterRole) || count("SELECT COUNT(*) FROM app_user WHERE id=? AND enabled=TRUE", invitation.inviter()) != 1) throw new BusinessException(409, "邀请人授权已失效，请联系团队所有者");
            assignable(inviterRole, invitation.role());
            if (role(id, actor.id()) != null) throw new BusinessException(409, "已加入团队");
            if (count("SELECT COUNT(*) FROM team_member WHERE team_id=?", id) >= 100) throw new BusinessException(409, "团队成员已达上限");
            jdbc.update("INSERT INTO team_member(team_id,user_id,role) VALUES(?,?,?)", id, actor.id(), invitation.role());
        }
        jdbc.update("UPDATE team_invitation SET status=? WHERE id=?", accept ? "accepted" : "declined", invitationId);
        audit.record(actor, "TEAM_INVITE_RESPOND", id + ":invite:" + invitationId + ":" + (accept ? "accept" : "decline"), "SUCCESS");
    }

    @Transactional
    public void cancelInvite(SessionUser actor, long id, long invitationId) {
        lock(id);
        String actorRole = requireManager(id, actor.id()); requireActive(id);
        var targets = jdbc.queryForList("SELECT role FROM team_invitation WHERE id=? AND team_id=? AND status='pending'", String.class, invitationId, id);
        if (targets.isEmpty()) throw missing();
        assignable(actorRole, targets.get(0));
        jdbc.update("UPDATE team_invitation SET status='cancelled' WHERE id=?", invitationId);
        audit.record(actor, "TEAM_INVITE_CANCEL", id + ":invite:" + invitationId, "SUCCESS");
    }

    @Transactional
    public InviteLink createInviteLink(SessionUser actor, long id, String role) {
        lock(id);
        String actorRole = requireManager(id, actor.id()); requireActive(id);
        assignable(actorRole, role);
        if (count("SELECT COUNT(*) FROM team_invite_link WHERE team_id=? AND status='active' AND expires_at>?", id, Timestamp.from(Instant.now())) >= 20) throw new BusinessException(409, "有效邀请链接已达上限，请先撤销旧链接");
        String token = newInviteToken();
        String hash = inviteTokenHash(token);
        Timestamp expiresAt = Timestamp.from(Instant.now().plus(7, ChronoUnit.DAYS));
        jdbc.update("INSERT INTO team_invite_link(team_id,token_hash,role,created_by,expires_at) VALUES(?,?,?,?,?)", id, hash, role, actor.id(), expiresAt);
        long linkId = jdbc.queryForObject("SELECT id FROM team_invite_link WHERE token_hash=?", Long.class, hash);
        activity.record(actor, id, "TEAM_INVITE_LINK_CREATE", "link:" + linkId);
        audit.record(actor, "TEAM_INVITE_LINK_CREATE", id + ":link:" + linkId + ":" + role, "SUCCESS");
        return new InviteLink(linkId, id, role, token, expiresAt.toInstant().toString());
    }

    public List<InviteLinkSummary> inviteLinks(SessionUser actor, long id) {
        requireManager(id, actor.id());
        if (jdbc.queryForList("SELECT id FROM team_workspace WHERE id=?", Long.class, id).isEmpty()) throw missing();
        return jdbc.query("SELECT l.id,l.role,l.status,l.expires_at,l.created_at,u.username AS used_by_name FROM team_invite_link l LEFT JOIN app_user u ON u.id=l.used_by WHERE l.team_id=? ORDER BY l.id DESC LIMIT 50",
                (result, row) -> new InviteLinkSummary(result.getLong("id"), result.getString("role"), result.getString("status"), result.getString("used_by_name"), result.getTimestamp("expires_at").toInstant().toString(), result.getTimestamp("created_at").toInstant().toString()), id);
    }

    public InviteLinkPreview previewInviteLink(SessionUser actor, String token) {
        if (token == null || token.isBlank() || token.length() > 128) throw new BusinessException(404, "邀请链接无效或已失效");
        var links = jdbc.query("SELECT l.id,l.team_id,l.role,l.created_by,l.status,l.expires_at,t.name AS team_name,t.status AS team_status,u.username AS creator_name FROM team_invite_link l JOIN team_workspace t ON t.id=l.team_id JOIN app_user u ON u.id=l.created_by WHERE l.token_hash=?",
                (result, row) -> new LinkRow(result.getLong("id"), result.getLong("team_id"), result.getString("role"), result.getLong("created_by"), result.getString("status"), result.getTimestamp("expires_at").toInstant(), result.getString("team_name"), result.getString("team_status"), result.getString("creator_name")), inviteTokenHash(token));
        if (links.isEmpty()) throw new BusinessException(404, "邀请链接无效或已失效");
        LinkRow link = links.get(0);
        String creatorRole = role(link.teamId(), link.createdBy());
        boolean valid = "active".equals(link.status()) && link.expiresAt().isAfter(Instant.now()) && "active".equals(link.teamStatus()) && manages(creatorRole);
        return new InviteLinkPreview(link.teamId(), link.teamName(), link.teamStatus(), link.role(), link.creatorName(), link.expiresAt().toString(), valid, role(link.teamId(), actor.id()) != null);
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public long acceptInviteLink(SessionUser actor, String token) {
        if (token == null || token.isBlank() || token.length() > 128) throw new BusinessException(404, "邀请链接无效或已失效");
        var links = jdbc.queryForList("SELECT team_id FROM team_invite_link WHERE token_hash=?", Long.class, inviteTokenHash(token));
        if (links.isEmpty()) throw new BusinessException(404, "邀请链接无效或已失效");
        long id = links.get(0); lock(id);
        var rows = jdbc.query("SELECT id,role,created_by,status,expires_at FROM team_invite_link WHERE token_hash=? FOR UPDATE",
                (result, row) -> new LinkRow(result.getLong("id"), id, result.getString("role"), result.getLong("created_by"), result.getString("status"), result.getTimestamp("expires_at").toInstant(), null, null, null), inviteTokenHash(token));
        if (rows.isEmpty()) throw new BusinessException(404, "邀请链接无效或已失效");
        LinkRow link = rows.get(0);
        if (!"active".equals(link.status()) || !link.expiresAt().isAfter(Instant.now())) throw new BusinessException(409, "邀请链接已使用、撤销或过期");
        requireActive(id);
        String creatorRole = role(id, link.createdBy());
        if (!manages(creatorRole) || count("SELECT COUNT(*) FROM app_user WHERE id=? AND enabled=TRUE", link.createdBy()) != 1) throw new BusinessException(409, "邀请人授权已失效，请联系团队所有者");
        assignable(creatorRole, link.role());
        if (role(id, actor.id()) != null) throw new BusinessException(409, "已加入团队");
        if (count("SELECT COUNT(*) FROM team_member WHERE team_id=?", id) >= 100) throw new BusinessException(409, "团队成员已达上限");
        jdbc.update("INSERT INTO team_member(team_id,user_id,role) VALUES(?,?,?)", id, actor.id(), link.role());
        jdbc.update("UPDATE team_invite_link SET status='used',used_by=?,used_at=? WHERE id=? AND status='active'", actor.id(), Timestamp.from(Instant.now()), link.id());
        activity.record(actor, id, "TEAM_INVITE_LINK_JOIN", "link:" + link.id());
        audit.record(actor, "TEAM_INVITE_LINK_JOIN", id + ":link:" + link.id() + ":" + link.role(), "SUCCESS");
        return id;
    }

    @Transactional
    public void revokeInviteLink(SessionUser actor, long id, long linkId) {
        lock(id);
        String actorRole = requireManager(id, actor.id()); requireActive(id);
        var roles = jdbc.queryForList("SELECT role FROM team_invite_link WHERE id=? AND team_id=? AND status='active'", String.class, linkId, id);
        if (roles.isEmpty()) throw missing();
        assignable(actorRole, roles.get(0));
        jdbc.update("UPDATE team_invite_link SET status='revoked' WHERE id=?", linkId);
        activity.record(actor, id, "TEAM_INVITE_LINK_REVOKE", "link:" + linkId);
        audit.record(actor, "TEAM_INVITE_LINK_REVOKE", id + ":link:" + linkId, "SUCCESS");
    }

    @Transactional
    public void changeMember(SessionUser actor, long id, long target, String nextRole) {
        lock(id);
        String actorRole = requireManager(id, actor.id()); requireActive(id);
        String targetRole = requireMember(id, target);
        if (actor.id() == target || "owner".equals(targetRole)) throw new BusinessException(403, "不可修改自己或团队所有者");
        assignable(actorRole, targetRole); assignable(actorRole, nextRole);
        jdbc.update("UPDATE team_member SET role=? WHERE team_id=? AND user_id=?", nextRole, id, target);
        cancelIssued(id, target);
        audit.record(actor, "TEAM_MEMBER_ROLE", id + ":user:" + target + ":" + nextRole, "SUCCESS");
    }

    @Transactional
    public void removeMember(SessionUser actor, long id, long target) {
        lock(id);
        String actorRole = requireMember(id, actor.id());
        String targetRole = requireMember(id, target);
        if ("owner".equals(targetRole)) throw new BusinessException(403, "团队所有者不能退出或被移除");
        if (actor.id() != target) { requireActive(id); assignable(actorRole, targetRole); }
        jdbc.update("DELETE FROM team_member WHERE team_id=? AND user_id=?", id, target);
        cancelIssued(id, target);
        audit.record(actor, "TEAM_MEMBER_REMOVE", id + ":user:" + target, "SUCCESS");
    }

    public Page<Team> adminList(SessionUser actor, String query, String status, int page, int pageSize) {
        requireAdmin(actor); SecurityAuditService.validatePage(page, pageSize);
        if (query != null && query.length() > 80) throw new BusinessException(400, "检索词过长");
        String where = " WHERE 1=1";
        var values = new ArrayList<Object>();
        if (query != null && !query.isBlank()) { where += " AND LOCATE(LOWER(?),LOWER(t.name))>0"; values.add(query.trim()); }
        if (status != null && !status.isBlank()) { validStatus(status); where += " AND t.status=?"; values.add(status); }
        long total = count("SELECT COUNT(*) FROM team_workspace t" + where, values.toArray());
        values.add(pageSize); values.add((page - 1L) * pageSize);
        var items = jdbc.query("SELECT t.*,NULL AS role,u.username AS owner_name,(SELECT COUNT(*) FROM team_member m WHERE m.team_id=t.id) AS member_count FROM team_workspace t JOIN app_user u ON u.id=t.owner_id" + where + " ORDER BY t.id DESC LIMIT ? OFFSET ?", (result, row) -> team(result), values.toArray());
        return new Page<>(items, total, page, pageSize);
    }

    public List<Member> adminMembers(SessionUser actor, long id) { requireAdmin(actor); teamById(id, null); return members(id); }

    @Transactional
    public void setStatus(SessionUser actor, long id, String status) {
        accounts.requireMutationAuthority(actor, true); validStatus(status); lock(id);
        jdbc.update("UPDATE team_workspace SET status=? WHERE id=?", status, id);
        if ("frozen".equals(status)) {
            jdbc.update("UPDATE team_agent_run SET status='EXPIRED',grant_token=NULL WHERE team_id=? AND status IN ('APPROVED','PENDING_APPROVAL')", id);
        }
        activity.record(actor, id, "TEAM_STATUS", status);
        audit.record(actor, "TEAM_STATUS", id + ":" + status, "SUCCESS");
    }

    private static final SecureRandom INVITE_RANDOM = new SecureRandom();
    private String newInviteToken() {
        byte[] value = new byte[32];
        INVITE_RANDOM.nextBytes(value);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }
    private String inviteTokenHash(String token) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException failure) {
            throw new IllegalStateException("SHA-256 unavailable", failure);
        }
    }
    private void cancelIssued(long id, long userId) { jdbc.update("UPDATE team_invitation SET status='cancelled' WHERE team_id=? AND invited_by=? AND status='pending'", id, userId); }
    private void lock(long id) { if (jdbc.queryForList("SELECT id FROM team_workspace WHERE id=? FOR UPDATE", Long.class, id).isEmpty()) throw missing(); }
    private void requireActive(long id) { if (!"active".equals(jdbc.queryForObject("SELECT status FROM team_workspace WHERE id=?", String.class, id))) throw new BusinessException(403, "团队已冻结，请联系平台管理员"); }
    private String role(long id, long userId) { var roles = jdbc.queryForList("SELECT role FROM team_member WHERE team_id=? AND user_id=?", String.class, id, userId); return roles.isEmpty() ? null : roles.get(0); }
    private String requireMember(long id, long userId) { String role = role(id, userId); if (role == null) throw missing(); return role; }
    private String requireManager(long id, long userId) { String role = requireMember(id, userId); if (!manages(role)) throw new BusinessException(403, "需要团队所有者或管理员权限"); return role; }
    private boolean manages(String role) { return "owner".equals(role) || "admin".equals(role); }
    private void assignable(String actorRole, String role) {
        if (!List.of("admin", "specialist", "member", "viewer").contains(role)) throw new BusinessException(400, "团队角色无效");
        if (!manages(actorRole) || "admin".equals(role) && !"owner".equals(actorRole)) throw new BusinessException(403, "只有团队所有者可以管理团队管理员");
        if ("specialist".equals(role) && !List.of("owner", "admin").contains(actorRole)) throw new BusinessException(403, "只有团队负责人或副负责人可以任命专项负责人");
    }
    /** 管理端团队视图要求平台 teams.view 能力，避免被撤销的管理员仅凭 admin 角色继续读取。 */
    private void requireAdmin(SessionUser actor) {
        if (actor == null || !"admin".equals(actor.role()) || !"admin".equals(actor.portal())) throw new BusinessException(403, "需要管理层会话");
        accounts.requirePlatformCapability(actor, "teams.view");
    }
    private void validStatus(String status) { if (!List.of("active", "frozen").contains(status)) throw new BusinessException(400, "团队状态无效"); }
    private long count(String sql, Object... values) { return jdbc.queryForObject(sql, Long.class, values); }
    private String text(String value, int maximum) { if (value == null || value.isBlank() || value.trim().length() > maximum || value.chars().anyMatch(Character::isISOControl)) throw new BusinessException(400, "名称或用户名无效"); return value.trim(); }
    private String description(String value) { if (value == null) return ""; if (value.length() > 500) throw new BusinessException(400, "团队描述最多 500 字"); return value.trim(); }
    private BusinessException missing() { return new BusinessException(404, "团队资源不存在或无权访问"); }
    private Team teamById(long id, String role) {
        var teams = jdbc.query("SELECT t.*,? AS role,u.username AS owner_name,(SELECT COUNT(*) FROM team_member m WHERE m.team_id=t.id) AS member_count FROM team_workspace t JOIN app_user u ON u.id=t.owner_id WHERE t.id=?", (result, row) -> team(result), role, id);
        if (teams.isEmpty()) throw missing(); return teams.get(0);
    }
    private List<Member> members(long id) { return jdbc.query("SELECT m.user_id,u.username,m.role,u.enabled FROM team_member m JOIN app_user u ON u.id=m.user_id WHERE m.team_id=? ORDER BY m.joined_at,m.user_id", (result, row) -> new Member(result.getLong("user_id"), result.getString("username"), result.getString("role"), result.getBoolean("enabled")), id); }
    private String invitationSelect() { return "SELECT i.id,i.team_id,t.name AS team_name,t.status AS team_status,u.username,i.role,i.expires_at FROM team_invitation i JOIN team_workspace t ON t.id=i.team_id JOIN app_user u ON u.id=i.invitee_id"; }
    private List<Invitation> invitationsForTeam(long id) { return jdbc.query(invitationSelect() + " WHERE i.team_id=? AND i.status='pending' AND i.expires_at>? ORDER BY i.id DESC", (result, row) -> invitation(result), id, Timestamp.from(Instant.now())); }
    private Team team(java.sql.ResultSet result) throws java.sql.SQLException { return new Team(result.getLong("id"), result.getString("name"), result.getString("description"), result.getLong("owner_id"), result.getString("owner_name"), result.getString("status"), result.getString("role"), result.getLong("member_count"), result.getTimestamp("created_at").toInstant().toString()); }
    private Invitation invitation(java.sql.ResultSet result) throws java.sql.SQLException { return new Invitation(result.getLong("id"), result.getLong("team_id"), result.getString("team_name"), result.getString("team_status"), result.getString("username"), result.getString("role"), result.getTimestamp("expires_at").toInstant().toString()); }
    private record Pending(long inviter, String role) {}
    private record LinkRow(long id, long teamId, String role, long createdBy, String status, Instant expiresAt, String teamName, String teamStatus, String creatorName) {}
    public record InviteLink(long id, long teamId, String role, String token, String expiresAt) {}
    public record InviteLinkSummary(long id, String role, String status, String usedBy, String expiresAt, String createdAt) {}
    public record InviteLinkPreview(long teamId, String teamName, String teamStatus, String role, String creatorName, String expiresAt, boolean valid, boolean member) {}
    public record Team(long id, String name, String description, long ownerId, String ownerName, String status, String role, long memberCount, String createdAt) {}
    public record Member(long userId, String username, String role, boolean enabled) {}
    public record Invitation(long id, long teamId, String teamName, String teamStatus, String username, String role, String expiresAt) {}
    public record Detail(Team team, List<Member> members, List<Invitation> invitations) {}
    public record Page<T>(List<T> items, long total, int page, int pageSize) {}
}
