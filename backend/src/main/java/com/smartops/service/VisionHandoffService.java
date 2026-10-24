package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class VisionHandoffService {
    private final JdbcTemplate jdbc;
    private final PersonalKnowledgeService knowledge;
    private final OperatorMemoryService memory;
    public VisionHandoffService(JdbcTemplate jdbc, PersonalKnowledgeService knowledge, OperatorMemoryService memory) { this.jdbc = jdbc; this.knowledge = knowledge; this.memory = memory; }

    public PersonalKnowledgeService.Entry toPersonalKnowledge(Long userId, String eventId, Long libraryId, String title) {
        Event event = event(userId, eventId);
        ensureConfirmed(event);
        String text = event.ocrText() == null || event.ocrText().isBlank() ? "视觉事件已确认，尚无 OCR 文本。" : event.ocrText();
        return knowledge.createEntry(userId, libraryId, title, "由用户确认的视觉证据", "# 视觉证据\n\n" + text, "VISION_EVENT", "vision:" + eventId);
    }

    public OperatorMemoryService.Memory toMemory(Long userId, String eventId, String incidentKey, String action) {
        Event event = event(userId, eventId);
        ensureConfirmed(event);
        return memory.recordConfirmed(userId, incidentKey, "VISION_EVENT", action, "vision:" + eventId);
    }

    private void ensureConfirmed(Event event) { if (!event.confirmed()) throw new BusinessException(409, "VISION_EVENT_NOT_CONFIRMED"); if (!"READY".equals(event.ocrStatus())) throw new BusinessException(409, "VISION_EVENT_NOT_READY"); }
    private Event event(Long userId, String id) { List<Event> rows = jdbc.query("SELECT id,user_id,ocr_status,user_confirmed,ocr_text FROM vision_event WHERE id=? AND user_id=?", (rs, row) -> new Event(rs.getString("id"), rs.getString("ocr_status"), rs.getBoolean("user_confirmed"), rs.getString("ocr_text")), id, userId); if (rows.isEmpty()) throw new BusinessException(404, "VISION_EVENT_NOT_FOUND"); return rows.get(0); }
    private record Event(String id, String ocrStatus, boolean confirmed, String ocrText) {}
}
