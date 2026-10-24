package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.UserAccountService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.web.multipart.MultipartFile;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import static com.smartops.service.ChatAttachmentValidator.MB;

@Service
@Transactional(isolation = Isolation.READ_COMMITTED)
public class ChatAttachmentService {
    private final JdbcTemplate jdbc;
    private final SecurityAuditService audit;
    private final UserAccountService accounts;
    private final VisionEventService visionEvents;
    private static final Set<String> VISUAL_SOURCES = Set.of("FILE", "SCREENSHOT", "CAMERA", "CLIPBOARD", "DRAG_DROP");
    private static final String RECEIPT = "附件及文字已保存到当前私有会话。当前阶段尚未接入 OCR、图片理解或附件内容分析，内容未发送给任何模型，也未自动进入知识库。可预览、下载，或删除会话清除附件。文本问答请新建普通对话。";

    public ChatAttachmentService(JdbcTemplate jdbc, SecurityAuditService audit, UserAccountService accounts, VisionEventService visionEvents) { this.jdbc = jdbc; this.audit = audit; this.accounts = accounts; this.visionEvents = visionEvents; }

    public List<Conversation> list(SessionUser user, Long teamId) {
        String scope = lockScope(user, teamId, false);
        cleanup(scope);
        return jdbc.query("SELECT * FROM chat_conversation WHERE scope_key=? ORDER BY updated_at DESC LIMIT 100", (row, index) -> conversation(row), scope);
    }

    public Conversation create(SessionUser user, String id, String title, Long teamId) {
        uuid(id);
        String scope = lockScope(user, teamId, true);
        var existing = find(id);
        if (existing != null) {
            if (!existing.scopeKey().equals(scope) || existing.ownerId() != user.id()) throw new BusinessException(404, "会话不存在");
            return existing;
        }
        if (count("SELECT COUNT(*) FROM chat_conversation WHERE scope_key=?", scope) >= 100) throw new BusinessException(409, "附件会话已达 100 个，请先删除不再需要的会话");
        long now = System.currentTimeMillis();
        jdbc.update("INSERT INTO chat_conversation(id,owner_id,team_id,scope_key,title,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                id, user.id(), teamId, scope, title.trim(), now, now);
        audit.record(user, "CHAT_CONVERSATION_CREATE", id, "SUCCESS");
        return find(id);
    }

    public Detail detail(SessionUser user, String id) {
        Conversation current = require(user, id, false);
        cleanup(current.scopeKey());
        return detail(current);
    }

    public void rename(SessionUser user, String id, String title) {
        require(user, id, true);
        jdbc.update("UPDATE chat_conversation SET title=?,updated_at=? WHERE id=?", title.trim(), System.currentTimeMillis(), id);
    }

    public void delete(SessionUser user, String id) {
        Conversation current = require(user, id, true);
        if (current.ownerId() != user.id() && current.teamId() != null) {
            String role = jdbc.queryForObject("SELECT role FROM team_member WHERE team_id=? AND user_id=?", String.class, current.teamId(), user.id());
            if (!Set.of("owner", "admin").contains(role)) throw new BusinessException(403, "只有创建者或团队管理员可删除会话");
        }
        jdbc.update("DELETE FROM chat_conversation WHERE id=?", id);
        audit.record(user, "CHAT_CONVERSATION_DELETE", id, "SUCCESS");
    }

    public Attachment upload(SessionUser user, String id, String requestId, MultipartFile file, String sourceType) {
        uuid(requestId);
        if (sourceType == null || !VISUAL_SOURCES.contains(sourceType)) throw new BusinessException(400, "附件来源无效");
        Conversation current = require(user, id, true);
        cleanup(current.scopeKey());
        var validated = ChatAttachmentValidator.validate(file);
        var prior = jdbc.query("SELECT * FROM chat_attachment WHERE conversation_id=? AND request_id=?", (row, index) -> attachment(row), id, requestId);
        if (!prior.isEmpty()) {
            String hash = jdbc.queryForObject("SELECT request_hash FROM chat_attachment WHERE id=?", String.class, prior.get(0).id());
            if (!validated.requestHash().equals(hash)) throw new BusinessException(409, "上传标识已用于不同文件，请重新选择文件");
            if (!sourceType.equals(prior.get(0).sourceType())) throw new BusinessException(409, "上传标识已用于不同的附件来源");
            return prior.get(0);
        }
        long bytes = count("SELECT COALESCE(SUM(a.byte_size),0) FROM chat_attachment a JOIN chat_conversation c ON c.id=a.conversation_id WHERE c.scope_key=?", current.scopeKey());
        if (bytes + validated.bytes().length > 200 * MB) throw new BusinessException(409, "当前空间附件已达 200 MB 配额，请先清理会话");
        if (count("SELECT COUNT(*) FROM chat_attachment WHERE conversation_id=? AND message_id IS NULL", id) >= 5) throw new BusinessException(409, "该会话已有 5 个待发送附件，请先发送或删除");
        long stagedBytes = count("SELECT COALESCE(SUM(byte_size),0) FROM chat_attachment WHERE conversation_id=? AND message_id IS NULL", id);
        if (stagedBytes + validated.bytes().length > 40 * MB) throw new BusinessException(409, "待发送附件合计不能超过 40 MB");
        String attachmentId = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO chat_attachment(id,conversation_id,request_id,request_hash,name,media_type,source_type,byte_size,content,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                attachmentId, id, requestId, validated.requestHash(), validated.name(), validated.mediaType(), sourceType, validated.bytes().length, validated.bytes(), System.currentTimeMillis());
        audit.record(user, "CHAT_ATTACHMENT_UPLOAD", attachmentId, "SUCCESS");
        return new Attachment(attachmentId, validated.name(), validated.mediaType(), sourceType, validated.bytes().length);
    }

    @Transactional(isolation = Isolation.READ_COMMITTED, noRollbackFor = BusinessException.class)
    public Download download(SessionUser user, String id, String attachmentId) {
        Conversation current = require(user, id, false);
        cleanup(current.scopeKey());
        var rows = jdbc.query("SELECT * FROM chat_attachment WHERE id=? AND conversation_id=?", (row, index) -> new Download(attachment(row), row.getBytes("content")), attachmentId, id);
        if (rows.isEmpty()) throw new BusinessException(404, "附件不存在或已过期");
        return rows.get(0);
    }

    public void removeStaged(SessionUser user, String id, String attachmentId) {
        require(user, id, true);
        int removed = jdbc.update("DELETE FROM chat_attachment WHERE id=? AND conversation_id=? AND message_id IS NULL", attachmentId, id);
        if (removed == 0) throw new BusinessException(404, "待发送附件不存在；已发送附件请通过删除会话清除");
    }

    public Detail append(SessionUser user, String id, String requestId, String text, List<String> attachmentIds) {
        uuid(requestId);
        Conversation current = require(user, id, true);
        cleanup(current.scopeKey());
        if (attachmentIds == null) attachmentIds = List.of();
        if (text == null) text = "";
        text = text.trim();
        if (text.length() > 2000 || attachmentIds.size() > 5 || (text.isEmpty() && attachmentIds.isEmpty()) || Set.copyOf(attachmentIds).size() != attachmentIds.size()) throw new BusinessException(400, "消息或附件数量无效");
        String hash = ChatAttachmentValidator.digest(user.id() + "\n" + text + "\n" + String.join(",", attachmentIds));
        var prior = jdbc.queryForList("SELECT request_hash FROM chat_message WHERE conversation_id=? AND request_id=? AND role='user'", String.class, id, requestId);
        if (!prior.isEmpty()) {
            if (!prior.get(0).equals(hash)) throw new BusinessException(409, "发送标识已用于不同消息，请刷新后重试");
            return detail(current);
        }
        if (count("SELECT COUNT(*) FROM chat_message WHERE conversation_id=?", id) >= 200) throw new BusinessException(409, "会话消息达到上限，请新建会话");
        long bytes = 0;
        for (String attachmentId : attachmentIds) {
            uuid(attachmentId);
            var rows = jdbc.queryForList("SELECT byte_size,message_id FROM chat_attachment WHERE id=? AND conversation_id=?", attachmentId, id);
            if (rows.isEmpty()) throw new BusinessException(404, "附件不存在或不属于当前会话");
            if (rows.get(0).get("message_id") != null) throw new BusinessException(409, "附件已绑定到其他消息");
            bytes += ((Number) rows.get(0).get("byte_size")).longValue();
        }
        if (bytes > 40 * MB) throw new BusinessException(400, "每条消息附件不能超过 40 MB");
        long now = System.currentTimeMillis();
        String messageId = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO chat_message(id,conversation_id,request_id,request_hash,actor_id,role,content,created_at) VALUES(?,?,?,?,?,'user',?,?)", messageId, id, requestId, hash, user.id(), text, now);
        for (String attachmentId : attachmentIds) jdbc.update("UPDATE chat_attachment SET message_id=? WHERE id=? AND conversation_id=?", messageId, attachmentId, id);
        for (String attachmentId : attachmentIds) {
            var source = jdbc.queryForMap("SELECT media_type,source_type FROM chat_attachment WHERE id=? AND conversation_id=?", attachmentId, id);
            if (String.valueOf(source.get("media_type")).startsWith("image/")) visionEvents.create(user.id(), id, attachmentId, String.valueOf(source.get("source_type")));
        }
        jdbc.update("INSERT INTO chat_message(id,conversation_id,request_id,request_hash,actor_id,role,content,created_at) VALUES(?,?,?,?,?,'assistant',?,?)", UUID.randomUUID().toString(), id, requestId, hash, user.id(), RECEIPT, now + 1);
        jdbc.update("UPDATE chat_conversation SET updated_at=? WHERE id=?", now, id);
        return detail(find(id));
    }

    private Conversation require(SessionUser user, String id, boolean write) {
        uuid(id);
        Conversation current = find(id);
        if (current == null || (current.teamId() == null && current.ownerId() != user.id())) throw new BusinessException(404, "会话不存在");
        String scope = lockScope(user, current.teamId(), write);
        current = find(id);
        if (current == null || !current.scopeKey().equals(scope)) throw new BusinessException(404, "会话不存在");
        return current;
    }

    private String lockScope(SessionUser user, Long teamId, boolean write) {
        if (user == null || jdbc.queryForList("SELECT id FROM app_user WHERE id=? FOR UPDATE", Long.class, user.id()).isEmpty()
                || !accounts.isCurrent(user)) throw new BusinessException(401, "账号权限或密码已变更，请重新登录");
        if (user.mustChangePassword()) throw new BusinessException(403, "请先修改初始密码");
        if (teamId == null) {
            return "user:" + user.id();
        }
        var teams = jdbc.queryForList("SELECT status FROM team_workspace WHERE id=? FOR UPDATE", String.class, teamId);
        var roles = jdbc.queryForList("SELECT role FROM team_member WHERE team_id=? AND user_id=?", String.class, teamId, user.id());
        if (teams.isEmpty() || roles.isEmpty()) throw new BusinessException(404, "空间不存在");
        if (!"active".equals(teams.get(0))) throw new BusinessException(409, "团队已冻结，无法访问附件会话");
        if (write && !Set.of("owner", "admin", "member").contains(roles.get(0))) throw new BusinessException(403, "当前团队角色仅可读取");
        return "team:" + teamId;
    }

    private void cleanup(String scope) {
        jdbc.update("DELETE FROM chat_attachment WHERE message_id IS NULL AND created_at<? AND conversation_id IN (SELECT id FROM chat_conversation WHERE scope_key=?)", System.currentTimeMillis() - 86_400_000L, scope);
    }

    private Detail detail(Conversation current) {
        List<Message> messages = jdbc.query("SELECT * FROM chat_message WHERE conversation_id=? ORDER BY created_at,id", (row, index) -> {
            String messageId = row.getString("id");
            var attachments = jdbc.query("SELECT id,name,media_type,source_type,byte_size FROM chat_attachment WHERE message_id=? ORDER BY created_at,id", (attachmentRow, attachmentIndex) -> attachment(attachmentRow), messageId);
            boolean receipt = row.getString("role").equals("assistant");
            return new Message(messageId, row.getString("role"), row.getString("content"), receipt ? "attachment-receipt" : null, attachments);
        }, current.id());
        return new Detail(current.id(), current.title(), current.createdAt(), current.updatedAt(), current.teamId(), messages);
    }

    private Conversation find(String id) {
        var rows = jdbc.query("SELECT * FROM chat_conversation WHERE id=?", (row, index) -> conversation(row), id);
        return rows.isEmpty() ? null : rows.get(0);
    }
    private long count(String sql, Object... values) { return jdbc.queryForObject(sql, Long.class, values); }
    private Conversation conversation(ResultSet row) throws SQLException {
        long team = row.getLong("team_id"); Long teamId = row.wasNull() ? null : team;
        return new Conversation(row.getString("id"), row.getString("title"), row.getLong("owner_id"), teamId, row.getString("scope_key"), row.getLong("created_at"), row.getLong("updated_at"));
    }
    private Attachment attachment(ResultSet row) throws SQLException { return new Attachment(row.getString("id"), row.getString("name"), row.getString("media_type"), row.getString("source_type"), row.getLong("byte_size")); }
    private void uuid(String id) {
        if (id == null || !id.matches("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")) throw new BusinessException(400, "标识无效");
    }
    public record Conversation(String id, String title, long ownerId, Long teamId, String scopeKey, long createdAt, long updatedAt) {}
    public record Attachment(String id, String name, String mediaType, String sourceType, long size) {}
    public record Message(String id, String role, String content, String providerKey, List<Attachment> attachments) {}
    public record Detail(String id, String title, long createdAt, long updatedAt, Long teamId, List<Message> messages) {}
    public record Download(Attachment attachment, byte[] bytes) {}
}
