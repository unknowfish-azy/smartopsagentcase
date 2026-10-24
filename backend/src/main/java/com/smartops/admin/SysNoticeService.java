package com.smartops.admin;

import com.smartops.exception.BusinessException;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * 通知公告：区分"草稿/已发布"，发布打时间戳并写审计。
 */
@Service
public class SysNoticeService {

    private final JdbcTemplate jdbc;
    private final SecurityAuditService audit;

    public SysNoticeService(JdbcTemplate jdbc, SecurityAuditService audit) {
        this.jdbc = jdbc;
        this.audit = audit;
    }

    public List<Map<String, Object>> list(boolean includeDraft) {
        String sql = "SELECT id,title,type,status,publisher_name,published_at,created_at FROM sys_notice";
        if (!includeDraft) sql += " WHERE status=1 AND published_at IS NOT NULL";
        sql += " ORDER BY id DESC LIMIT 200";
        return jdbc.queryForList(sql);
    }

    @Transactional
    public Map<String, Object> create(SessionUser actor, String title, String content, int type) {
        KeyHolder keys = insert("""
                INSERT INTO sys_notice(title,content,type,status,publisher_id,publisher_name)
                VALUES(?,?,?,0,?,?)
                """, requireText(title, 200, "标题"), requireContent(content), normalizeType(type),
                actor == null ? null : actor.id(), actor == null ? "unknown" : actor.username());
        audit.record(actor, "NOTICE_CREATE", Long.toString(SysKeys.id(keys)), "SUCCESS");
        return byId(SysKeys.id(keys));
    }

    @Transactional
    public Map<String, Object> update(SessionUser actor, long id, String title, String content, int type) {
        requireExists(id);
        jdbc.update("UPDATE sys_notice SET title=?,content=?,type=? WHERE id=?",
                requireText(title, 200, "标题"), requireContent(content), normalizeType(type), id);
        audit.record(actor, "NOTICE_UPDATE", Long.toString(id), "SUCCESS");
        return byId(id);
    }

    @Transactional
    public void publish(SessionUser actor, long id) {
        requireExists(id);
        jdbc.update("UPDATE sys_notice SET status=1,published_at=? WHERE id=?", Timestamp.from(Instant.now()), id);
        audit.record(actor, "NOTICE_PUBLISH", Long.toString(id), "SUCCESS");
    }

    @Transactional
    public void delete(SessionUser actor, long id) {
        requireExists(id);
        jdbc.update("DELETE FROM sys_notice WHERE id=?", id);
        audit.record(actor, "NOTICE_DELETE", Long.toString(id), "SUCCESS");
    }

    private KeyHolder insert(String sql, Object... args) {
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS);
            for (int i = 0; i < args.length; i++) statement.setObject(i + 1, args[i]);
            return statement;
        }, keys);
        return keys;
    }

    private void requireExists(long id) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM sys_notice WHERE id=?", Integer.class, id);
        if (count == null || count == 0) throw new BusinessException(404, "公告不存在");
    }

    private Map<String, Object> byId(long id) {
        return jdbc.queryForList("""
                SELECT id,title,content,type,status,publisher_name,published_at,created_at FROM sys_notice WHERE id=?
                """, id).stream().findFirst().orElseThrow(() -> new BusinessException(404, "公告不存在"));
    }

    private static String requireText(String value, int max, String label) {
        if (value == null || value.isBlank()) throw new BusinessException(400, label + "不能为空");
        String trimmed = value.trim();
        if (trimmed.length() > max) throw new BusinessException(400, label + "不超过 " + max + " 字符");
        return trimmed;
    }

    private static String requireContent(String content) {
        if (content == null || content.isBlank()) throw new BusinessException(400, "公告内容不能为空");
        return content.trim();
    }

    private static int normalizeType(int type) {
        if (type != 1 && type != 2) throw new BusinessException(400, "公告类型需为 1（通知）或 2（公告）");
        return type;
    }
}
