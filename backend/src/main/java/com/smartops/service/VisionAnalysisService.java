package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Locale;

@Service
public class VisionAnalysisService {
    private final JdbcTemplate jdbc;
    public VisionAnalysisService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public Result recordOcr(Long userId, String eventId, String text, double confidence) {
        EventRow event = detail(userId, eventId);
        String value = text == null ? "" : text.trim();
        boolean sensitive = containsSensitive(value);
        String privacy = sensitive ? "REDACTION_REQUIRED" : "CLEAR";
        String analysis = confidence < 0.8 ? "MANUAL_REVIEW" : "READY_FOR_ANALYSIS";
        jdbc.update("UPDATE vision_event SET ocr_status='READY',analysis_status=?,privacy_status=?,ocr_text=?,confidence=?,updated_at=? WHERE id=? AND user_id=?", analysis, privacy, value, confidence, System.currentTimeMillis(), eventId, userId);
        return new Result(eventId, "READY", analysis, privacy, value, confidence);
    }

    private boolean containsSensitive(String text) {
        String value = text.toLowerCase(Locale.ROOT);
        return value.matches(".*(token|password|passwd|secret|private key|cookie)\\s*[=:].*") || value.matches(".*(sk-[a-z0-9]{12,}|ghp_[a-z0-9]{20,}).*");
    }

    private EventRow detail(Long userId, String id) { List<EventRow> rows = jdbc.query("SELECT id,user_id FROM vision_event WHERE id=? AND user_id=?", (rs, row) -> new EventRow(rs.getString("id"), rs.getLong("user_id")), id, userId); if (rows.isEmpty()) throw new BusinessException(404, "VISION_EVENT_NOT_FOUND"); return rows.get(0); }
    private record EventRow(String id, Long userId) {}
    public record Result(String eventId, String ocrStatus, String analysisStatus, String privacyStatus, String ocrText, double confidence) {}
}
