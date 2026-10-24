package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class SecurityNoticeService {
    private final JdbcTemplate jdbc;
    private final SecurityAuditService audit;
    public SecurityNoticeService(JdbcTemplate jdbc, SecurityAuditService audit) { this.jdbc = jdbc; this.audit = audit; }

    public void record(SessionUser user, String kind, String message) {
        jdbc.update("INSERT INTO account_security_notice(user_id,kind,message) VALUES(?,?,?)", user.id(), kind, message);
    }

    @Transactional
    public void failure(SessionUser user) {
        audit.record(user, "MFA_VERIFY", user.id().toString(), "FAILURE");
        record(user, "MFA_FAILURE", "密码通过后的二次认证未通过。若非本人操作，请修改密码并检查活动会话。");
    }

    public List<Notice> list(SessionUser user) {
        requireAdmin(user);
        return jdbc.query("SELECT id,kind,message,created_at,read_at FROM account_security_notice WHERE user_id=? ORDER BY id DESC LIMIT 50",
                (result, row) -> new Notice(result.getLong("id"), result.getString("kind"), result.getString("message"),
                        result.getTimestamp("created_at").toInstant().toString(), result.getTimestamp("read_at") != null), user.id());
    }

    public void read(SessionUser user, long id) {
        requireAdmin(user);
        if (jdbc.update("UPDATE account_security_notice SET read_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", id, user.id()) != 1) throw new BusinessException(404, "提醒不存在");
    }

    private static void requireAdmin(SessionUser user) {
        if (user == null || !"admin".equals(user.role()) || !"admin".equals(user.portal())) throw new BusinessException(403, "需要管理员入口");
    }
    public record Notice(long id, String kind, String message, String createdAt, boolean read) {}
}
