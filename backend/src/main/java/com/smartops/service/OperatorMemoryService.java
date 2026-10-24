package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

@Service
public class OperatorMemoryService {
    private final JdbcTemplate jdbc;
    public OperatorMemoryService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Transactional
    public Memory recordConfirmed(Long userId, String incidentKey, String memoryType, String preferredAction, String sourceRefs) {
        if (incidentKey == null || incidentKey.isBlank() || preferredAction == null || preferredAction.isBlank()) throw new BusinessException("OPERATOR_MEMORY_INPUT_REQUIRED");
        Instant now = Instant.now();
        jdbc.update("INSERT INTO operator_memory(user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", userId, incidentKey.trim(), memoryType == null ? "GENERAL" : memoryType.trim(), preferredAction.trim(), sourceRefs, 1, 0.5d, "ACTIVE", Timestamp.from(now), Timestamp.from(now));
        Long id = jdbc.queryForObject("SELECT MAX(id) FROM operator_memory WHERE user_id=?", Long.class, userId);
        return detail(userId, id);
    }

    public List<Memory> match(Long userId, String incidentKey) {
        String query = incidentKey == null ? "" : incidentKey.trim().toLowerCase();
        return jdbc.query("SELECT id,user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at FROM operator_memory WHERE user_id=? AND status='ACTIVE' AND LOWER(incident_key) LIKE ? ORDER BY confidence DESC,updated_at DESC", this::map, userId, "%" + query + "%");
    }

    public List<Memory> list(Long userId) { return jdbc.query("SELECT id,user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at FROM operator_memory WHERE user_id=? ORDER BY updated_at DESC,id DESC", this::map, userId); }

    @Transactional public void disable(Long userId, Long id) { detail(userId, id); jdbc.update("UPDATE operator_memory SET status='DISABLED',updated_at=? WHERE id=? AND user_id=?", Timestamp.from(Instant.now()), id, userId); }
    @Transactional public void delete(Long userId, Long id) { detail(userId, id); jdbc.update("DELETE FROM operator_memory WHERE id=? AND user_id=?", id, userId); }

    private Memory detail(Long userId, Long id) { List<Memory> rows = jdbc.query("SELECT id,user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at FROM operator_memory WHERE id=? AND user_id=?", this::map, id, userId); if (rows.isEmpty()) throw new BusinessException(404, "OPERATOR_MEMORY_NOT_FOUND"); return rows.get(0); }
    private Memory map(java.sql.ResultSet rs, int row) throws java.sql.SQLException { return new Memory(rs.getLong("id"), rs.getLong("user_id"), rs.getString("incident_key"), rs.getString("memory_type"), rs.getString("preferred_action"), rs.getString("source_refs"), rs.getInt("evidence_count"), rs.getDouble("confidence"), rs.getString("status"), rs.getTimestamp("created_at").toInstant(), rs.getTimestamp("updated_at").toInstant()); }
    public record Memory(Long id, Long userId, String incidentKey, String memoryType, String preferredAction, String sourceRefs, int evidenceCount, double confidence, String status, Instant createdAt, Instant updatedAt) {}
}
