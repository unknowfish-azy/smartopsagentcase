package com.smartops.service;

import com.smartops.security.SessionUser;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class TeamActivityService {
    private final JdbcTemplate jdbc;
    public TeamActivityService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public void record(SessionUser actor, long teamId, String action, String targetId) {
        jdbc.update("INSERT INTO team_activity_event(team_id,actor_id,action,target_id) VALUES(?,?,?,?)",
                teamId, actor == null ? null : actor.id(), action, targetId);
    }

    public List<Activity> list(long teamId, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 100));
        return jdbc.query("SELECT e.id,e.team_id,e.actor_id,COALESCE(u.username,'system') actor_username,e.action,e.target_id,e.created_at FROM team_activity_event e LEFT JOIN app_user u ON u.id=e.actor_id WHERE e.team_id=? ORDER BY e.id DESC LIMIT ?",
                (row, ignored) -> new Activity(row.getLong("id"), row.getLong("team_id"), row.getObject("actor_id", Long.class), row.getString("actor_username"), row.getString("action"), row.getString("target_id"), row.getTimestamp("created_at").toInstant().toString()), teamId, safeLimit);
    }

    public record Activity(long id, long teamId, Long actorId, String actorUsername, String action, String targetId, String createdAt) {}
}
