package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

@Service
public class ArtifactDraftService {
    private final JdbcTemplate jdbc;
    public ArtifactDraftService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Transactional
    public Draft createDraft(Long userId, String type, String title, String content, String sourceRef, String risk) {
        if (type == null || title == null || title.isBlank() || content == null || content.isBlank()) throw new BusinessException("ARTIFACT_DRAFT_INPUT_REQUIRED");
        Instant now = Instant.now();
        jdbc.update("INSERT INTO artifact_draft(user_id,artifact_type,title,content,status,risk,source_ref,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", userId, type.trim().toUpperCase(), title.trim(), content, "DRAFT", risk == null ? "READ_ONLY" : risk.trim().toUpperCase(), sourceRef, Timestamp.from(now), Timestamp.from(now));
        Long id = jdbc.queryForObject("SELECT MAX(id) FROM artifact_draft WHERE user_id=?", Long.class, userId);
        return detail(userId, id);
    }

    @Transactional
    public Draft submitReview(Long userId, Long id) {
        Draft draft = detail(userId, id);
        if (!"DRAFT".equals(draft.status())) throw new BusinessException(409, "ARTIFACT_DRAFT_NOT_EDITABLE");
        if (draft.content().length() < 10) throw new BusinessException(422, "ARTIFACT_DRAFT_TOO_SHORT");
        jdbc.update("UPDATE artifact_draft SET status='PENDING_REVIEW',updated_at=? WHERE id=? AND user_id=?", Timestamp.from(Instant.now()), id, userId);
        return detail(userId, id);
    }

    public List<Draft> list(Long userId) { return jdbc.query("SELECT id,user_id,artifact_type,title,content,status,risk,source_ref,created_at,updated_at FROM artifact_draft WHERE user_id=? ORDER BY updated_at DESC,id DESC", this::map, userId); }
    public Draft detail(Long userId, Long id) { List<Draft> rows = jdbc.query("SELECT id,user_id,artifact_type,title,content,status,risk,source_ref,created_at,updated_at FROM artifact_draft WHERE id=? AND user_id=?", this::map, id, userId); if (rows.isEmpty()) throw new BusinessException(404, "ARTIFACT_DRAFT_NOT_FOUND"); return rows.get(0); }
    private Draft map(java.sql.ResultSet rs, int row) throws java.sql.SQLException { return new Draft(rs.getLong("id"), rs.getLong("user_id"), rs.getString("artifact_type"), rs.getString("title"), rs.getString("content"), rs.getString("status"), rs.getString("risk"), rs.getString("source_ref"), rs.getTimestamp("created_at").toInstant(), rs.getTimestamp("updated_at").toInstant()); }
    public record Draft(Long id, Long userId, String artifactType, String title, String content, String status, String risk, String sourceRef, Instant createdAt, Instant updatedAt) {}
}
