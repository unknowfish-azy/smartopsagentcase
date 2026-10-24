package com.smartops.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.inspector.InspectionRecordRequest;
import com.smartops.dto.inspector.InspectionReplanRequest;
import com.smartops.dto.inspector.InspectionVerifyRequest;
import com.smartops.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class InspectorEventService {

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public Map<String, Object> summary() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", count("SELECT COUNT(*) FROM inspector_event"));
        result.put("pass", count("SELECT COUNT(*) FROM inspector_event WHERE status = 'PASS'"));
        result.put("warning", count("SELECT COUNT(*) FROM inspector_event WHERE status IN ('WARN', 'WARNING')"));
        result.put("high", count("SELECT COUNT(*) FROM inspector_event WHERE severity = 'HIGH'"));
        result.put("critical", count("SELECT COUNT(*) FROM inspector_event WHERE severity = 'CRITICAL'"));
        return result;
    }

    public List<Map<String, Object>> events(int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 200));
        return jdbcTemplate.queryForList(
                "SELECT id, task_id AS taskId, target, status, severity, category, "
                        + "agent_claim AS agentClaim, reason, recommendation, "
                        + "requires_human AS requiresHuman, created_at AS createdAt "
                        + "FROM inspector_event ORDER BY created_at DESC LIMIT ?",
                safeLimit
        );
    }

    public Map<String, Object> event(String id) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT id, task_id AS taskId, target, status, severity, category, "
                        + "agent_claim AS agentClaim, reason, recommendation, "
                        + "requires_human AS requiresHuman, metadata_json AS metadata, "
                        + "created_at AS createdAt FROM inspector_event WHERE id = ?",
                id
        );
        if (rows.isEmpty()) {
            throw new BusinessException(404, "纠察事件不存在");
        }

        Map<String, Object> result = new LinkedHashMap<>(rows.get(0));
        result.put("metadata", parseJson(result.get("metadata")));
        result.put("issues", jdbcTemplate.queryForList(
                "SELECT category, severity, reason, recommendation "
                        + "FROM inspector_issue WHERE event_id = ? ORDER BY id", id));
        result.put("evidence", jdbcTemplate.queryForList(
                "SELECT content, source, version, score "
                        + "FROM inspection_evidence WHERE event_id = ? ORDER BY id", id));
        List<Map<String, Object>> verification = jdbcTemplate.queryForList(
                "SELECT resolved, status, details_json AS details, verified_at AS verifiedAt "
                        + "FROM inspection_verification WHERE event_id = ? ORDER BY id DESC LIMIT 1",
                id
        );
        if (verification.isEmpty()) {
            result.put("verification", null);
        } else {
            Map<String, Object> latest = new LinkedHashMap<>(verification.get(0));
            latest.put("details", parseJson(latest.get("details")));
            result.put("verification", latest);
        }
        return result;
    }

    @Transactional
    public Map<String, Object> record(InspectionRecordRequest request) {
        String id = request.getInspectionId();
        if (id == null || id.isBlank()) {
            id = "INS-" + UUID.randomUUID().toString().replace("-", "")
                    .substring(0, 12).toUpperCase();
        }

        jdbcTemplate.update(
                "INSERT INTO inspector_event "
                        + "(id, task_id, target, status, severity, category, agent_claim, "
                        + "reason, recommendation, requires_human, metadata_json, created_at) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                id, request.getTaskId(), request.getTarget(), request.getStatus(),
                request.getSeverity(), request.getCategory(), request.getAgentClaim(),
                request.getReason(), request.getRecommendation(),
                Boolean.TRUE.equals(request.getRequiresHuman()),
                json(request.getMetadata()), LocalDateTime.now()
        );

        for (InspectionRecordRequest.Issue issue : request.getIssues()) {
            jdbcTemplate.update(
                    "INSERT INTO inspector_issue "
                            + "(event_id, category, severity, reason, recommendation) "
                            + "VALUES (?, ?, ?, ?, ?)",
                    id, issue.getCategory(), issue.getSeverity(),
                    issue.getReason(), issue.getRecommendation()
            );
        }

        for (InspectionRecordRequest.Evidence evidence : request.getEvidence()) {
            jdbcTemplate.update(
                    "INSERT INTO inspection_evidence "
                            + "(event_id, content, source, version, score) VALUES (?, ?, ?, ?, ?)",
                    id, evidence.getContent(), evidence.getSource(),
                    evidence.getVersion(), evidence.getScore()
            );
        }

        if (request.getVerification() != null) {
            saveVerification(id, request.getVerification().getResolved(),
                    request.getVerification().getStatus(),
                    request.getVerification().getDetails());
        }
        return event(id);
    }

    @Transactional
    public Map<String, Object> verify(InspectionVerifyRequest request) {
        ensureEvent(request.getInspectionId());
        saveVerification(request.getInspectionId(), request.getResolved(),
                request.getStatus(), request.getDetails());
        return event(request.getInspectionId());
    }

    public Map<String, Object> replan(InspectionReplanRequest request) {
        Map<String, Object> current = event(request.getInspectionId());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("inspectionId", request.getInspectionId());
        result.put("status", "REPLANNING");
        result.put("reason", request.getReason());
        result.put("recommendation", current.get("recommendation"));
        return result;
    }

    public Map<String, Object> statistics() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("summary", summary());
        result.put("byCategory", jdbcTemplate.queryForList(
                "SELECT category, COUNT(*) AS count FROM inspector_issue "
                        + "GROUP BY category ORDER BY count DESC"));
        result.put("byTarget", jdbcTemplate.queryForList(
                "SELECT target, COUNT(*) AS count FROM inspector_event "
                        + "GROUP BY target ORDER BY count DESC"));
        return result;
    }

    private long count(String sql) {
        Long value = jdbcTemplate.queryForObject(sql, Long.class);
        return value == null ? 0 : value;
    }

    private void ensureEvent(String id) {
        Long value = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM inspector_event WHERE id = ?",
                Long.class,
                id
        );
        if (value == null || value == 0) {
            throw new BusinessException(404, "纠察事件不存在");
        }
    }

    private void saveVerification(
            String id, Boolean resolved, String status, Map<String, Object> details
    ) {
        jdbcTemplate.update(
                "INSERT INTO inspection_verification "
                        + "(event_id, resolved, status, details_json, verified_at) "
                        + "VALUES (?, ?, ?, ?, ?)",
                id, resolved, status, json(details), LocalDateTime.now()
        );
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value == null ? Map.of() : value);
        } catch (JsonProcessingException ex) {
            throw new BusinessException("JSON 数据无法序列化");
        }
    }

    private Object parseJson(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return Map.of();
        }
        try {
            return objectMapper.readValue(
                    text, new TypeReference<Map<String, Object>>() {});
        } catch (JsonProcessingException ex) {
            return Map.of();
        }
    }
}
