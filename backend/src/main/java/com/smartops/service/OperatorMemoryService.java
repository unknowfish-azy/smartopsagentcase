package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
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
        try {
            // SEC-09：直接取本次插入的主键，避免同用户并发时 MAX(id) 取到别人的记录。
            long id = insertReturningId("INSERT INTO operator_memory(user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", userId, incidentKey.trim(), memoryType == null ? "GENERAL" : memoryType.trim(), preferredAction.trim(), sourceRefs, 1, 0.5d, "ACTIVE", Timestamp.from(now), Timestamp.from(now));
            return detail(userId, id);
        } catch (DuplicateKeyException e) {
            // SEC-10：(user_id, source_refs) 唯一键冲突——同来源记忆已存在，拒绝重复创建。
            throw new BusinessException(409, "OPERATOR_MEMORY_SOURCE_EXISTS");
        }
    }

    /**
     * 复盘学习回写：解决则证据+1、置信度上调并重新启用；未解决则置信度下调，过低时失效。
     */
    @Transactional
    public Memory feedback(Long userId, Long id, boolean resolved) {
        Memory memory = detail(userId, id);
        int evidenceCount = resolved ? memory.evidenceCount() + 1 : memory.evidenceCount();
        double confidence = resolved
                ? Math.min(0.95d, memory.confidence() + 0.1d)
                : Math.max(0.05d, memory.confidence() - 0.15d);
        String status = resolved ? "ACTIVE" : (confidence < 0.25d ? "DISABLED" : memory.status());
        jdbc.update("UPDATE operator_memory SET evidence_count=?,confidence=?,status=?,updated_at=? WHERE id=? AND user_id=?",
                evidenceCount, confidence, status, Timestamp.from(Instant.now()), id, userId);
        return detail(userId, id);
    }

    /** 复盘沉淀出的新记忆：首次经验，置信度略高于默认值。 */
    @Transactional
    public Memory recordLearned(Long userId, String incidentKey, String preferredAction, String sourceRefs) {
        if (incidentKey == null || incidentKey.isBlank() || preferredAction == null || preferredAction.isBlank()) return null;
        Instant now = Instant.now();
        try {
            long id = insertReturningId("INSERT INTO operator_memory(user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    userId, incidentKey.trim(), "DECISION_LOOP", preferredAction.trim(), sourceRefs, 1, 0.55d, "ACTIVE", Timestamp.from(now), Timestamp.from(now));
            return detail(userId, id);
        } catch (DuplicateKeyException e) {
            // SEC-10：唯一键冲突说明该 loop 已沉淀过记忆（review 幂等兜底），返回已有行即可。
            Memory existing = findBySourceRefs(userId, sourceRefs);
            return existing != null ? existing : null;
        }
    }

    /** 按 (user_id, source_refs) 查找已有记忆，用于唯一键冲突后的幂等回退。 */
    private Memory findBySourceRefs(Long userId, String sourceRefs) {
        List<Memory> rows = jdbc.query(
                "SELECT id,user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at "
                        + "FROM operator_memory WHERE user_id=? AND source_refs=? LIMIT 1",
                this::map, userId, sourceRefs);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Memory> byIds(Long userId, List<Long> ids) {
        if (ids == null || ids.isEmpty()) return List.of();
        String placeholders = String.join(",", ids.stream().map(item -> "?").toList());
        Object[] args = new Object[ids.size() + 1];
        args[0] = userId;
        for (int i = 0; i < ids.size(); i++) args[i + 1] = ids.get(i);
        return jdbc.query("SELECT id,user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at FROM operator_memory WHERE user_id=? AND id IN (" + placeholders + ") ORDER BY confidence DESC,updated_at DESC", this::map, args);
    }

    public List<Memory> match(Long userId, String incidentKey) {
        String query = incidentKey == null ? "" : incidentKey.trim().toLowerCase();
        return jdbc.query("SELECT id,user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at FROM operator_memory WHERE user_id=? AND status='ACTIVE' AND LOWER(incident_key) LIKE ? ORDER BY confidence DESC,updated_at DESC", this::map, userId, "%" + query + "%");
    }

    public List<Memory> list(Long userId) { return jdbc.query("SELECT id,user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at FROM operator_memory WHERE user_id=? ORDER BY updated_at DESC,id DESC", this::map, userId); }

    private long insertReturningId(String sql, Object... args) {
        var keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement(sql, new String[]{"id"});
            for (int i = 0; i < args.length; i++) statement.setObject(i + 1, args[i]);
            return statement;
        }, keys);
        return keys.getKey().longValue();
    }

    @Transactional public void disable(Long userId, Long id) { detail(userId, id); jdbc.update("UPDATE operator_memory SET status='DISABLED',updated_at=? WHERE id=? AND user_id=?", Timestamp.from(Instant.now()), id, userId); }
    @Transactional public void delete(Long userId, Long id) { detail(userId, id); jdbc.update("DELETE FROM operator_memory WHERE id=? AND user_id=?", id, userId); }

    private Memory detail(Long userId, Long id) { List<Memory> rows = jdbc.query("SELECT id,user_id,incident_key,memory_type,preferred_action,source_refs,evidence_count,confidence,status,created_at,updated_at FROM operator_memory WHERE id=? AND user_id=?", this::map, id, userId); if (rows.isEmpty()) throw new BusinessException(404, "OPERATOR_MEMORY_NOT_FOUND"); return rows.get(0); }
    private Memory map(java.sql.ResultSet rs, int row) throws java.sql.SQLException { return new Memory(rs.getLong("id"), rs.getLong("user_id"), rs.getString("incident_key"), rs.getString("memory_type"), rs.getString("preferred_action"), rs.getString("source_refs"), rs.getInt("evidence_count"), rs.getDouble("confidence"), rs.getString("status"), rs.getTimestamp("created_at").toInstant(), rs.getTimestamp("updated_at").toInstant()); }
    public record Memory(Long id, Long userId, String incidentKey, String memoryType, String preferredAction, String sourceRefs, int evidenceCount, double confidence, String status, Instant createdAt, Instant updatedAt) {}
}
