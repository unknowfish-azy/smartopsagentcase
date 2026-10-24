package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
public class VisionEventService {
    private final JdbcTemplate jdbc;
    public VisionEventService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Transactional
    public Event create(Long userId, String conversationId, String attachmentId, String sourceType) {
        var rows = jdbc.query("SELECT a.id,a.media_type,c.owner_id FROM chat_attachment a JOIN chat_conversation c ON c.id=a.conversation_id WHERE a.id=? AND a.conversation_id=? AND a.message_id IS NOT NULL AND c.owner_id=?", (rs, row) -> new Object[]{rs.getString("id"), rs.getString("media_type")}, attachmentId, conversationId, userId);
        if (rows.isEmpty() || !String.valueOf(rows.get(0)[1]).startsWith("image/")) throw new BusinessException(404, "VISION_ATTACHMENT_NOT_FOUND");
        var existing = jdbc.query("SELECT id,conversation_id,attachment_id,user_id,source_type,ocr_status,analysis_status,privacy_status,user_confirmed,created_at,updated_at FROM vision_event WHERE attachment_id=?", this::map, attachmentId);
        if (!existing.isEmpty()) return existing.get(0);
        String id = UUID.randomUUID().toString(); long now = System.currentTimeMillis();
        jdbc.update("INSERT INTO vision_event(id,conversation_id,attachment_id,user_id,source_type,ocr_status,analysis_status,privacy_status,user_confirmed,created_at,updated_at) VALUES(?,?,?,?,?,'QUEUED','NOT_STARTED','UNREVIEWED',FALSE,?,?)", id, conversationId, attachmentId, userId, sourceType == null ? "FILE" : sourceType, now, now);
        return detail(userId, id);
    }

    public Event markReady(Long userId, String id) { Event event = detail(userId, id); jdbc.update("UPDATE vision_event SET ocr_status='READY',updated_at=? WHERE id=? AND user_id=?", System.currentTimeMillis(), id, userId); return detail(userId, id); }
    public Event confirm(Long userId, String id) { Event event = detail(userId, id); if (!"READY".equals(event.ocrStatus())) throw new BusinessException(409, "VISION_EVENT_NOT_READY"); jdbc.update("UPDATE vision_event SET user_confirmed=TRUE,updated_at=? WHERE id=? AND user_id=?", System.currentTimeMillis(), id, userId); return detail(userId, id); }
    public List<Event> list(Long userId, String conversationId) { return jdbc.query("SELECT id,conversation_id,attachment_id,user_id,source_type,ocr_status,analysis_status,privacy_status,user_confirmed,created_at,updated_at FROM vision_event WHERE user_id=? AND conversation_id=? ORDER BY created_at DESC", this::map, userId, conversationId); }
    public Event detail(Long userId, String id) { List<Event> rows = jdbc.query("SELECT id,conversation_id,attachment_id,user_id,source_type,ocr_status,analysis_status,privacy_status,user_confirmed,created_at,updated_at FROM vision_event WHERE id=? AND user_id=?", this::map, id, userId); if (rows.isEmpty()) throw new BusinessException(404, "VISION_EVENT_NOT_FOUND"); return rows.get(0); }
    private Event map(java.sql.ResultSet rs, int row) throws java.sql.SQLException { return new Event(rs.getString("id"), rs.getString("conversation_id"), rs.getString("attachment_id"), rs.getLong("user_id"), rs.getString("source_type"), rs.getString("ocr_status"), rs.getString("analysis_status"), rs.getString("privacy_status"), rs.getBoolean("user_confirmed"), rs.getLong("created_at"), rs.getLong("updated_at")); }
    public record Event(String id, String conversationId, String attachmentId, Long userId, String sourceType, String ocrStatus, String analysisStatus, String privacyStatus, boolean userConfirmed, long createdAt, long updatedAt) {}
}
