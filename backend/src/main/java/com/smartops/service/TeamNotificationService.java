package com.smartops.service;

import com.smartops.security.SessionUser;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class TeamNotificationService {
    private final JdbcTemplate jdbc;
    public TeamNotificationService(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public List<Notification> list(SessionUser actor, boolean unreadOnly) {
        String filter = unreadOnly ? " AND read_at IS NULL" : "";
        return jdbc.query("SELECT id,team_id,notification_type,reference_id,message,read_at,created_at FROM team_notification WHERE user_id=?" + filter + " ORDER BY id DESC LIMIT 100",
                (row, ignored) -> new Notification(row.getLong("id"), row.getObject("team_id", Long.class), row.getString("notification_type"), row.getString("reference_id"), row.getString("message"), row.getTimestamp("read_at") == null ? null : row.getTimestamp("read_at").toInstant().toString(), row.getTimestamp("created_at").toInstant().toString()), actor.id());
    }
    @Transactional public void markRead(SessionUser actor, long id) { jdbc.update("UPDATE team_notification SET read_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND read_at IS NULL", id, actor.id()); }
    public void notifyUser(long userId, Long teamId, String type, String referenceId, String message) { jdbc.update("INSERT INTO team_notification(team_id,user_id,notification_type,reference_id,message) VALUES(?,?,?,?,?)", teamId, userId, type, referenceId, message); }
    public record Notification(long id, Long teamId, String type, String referenceId, String message, String readAt, String createdAt) {}
}
