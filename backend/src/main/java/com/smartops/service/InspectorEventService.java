package com.smartops.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.inspector.InspectionRecordRequest;
import com.smartops.dto.inspector.InspectionReplanRequest;
import com.smartops.dto.inspector.InspectionVerifyRequest;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRedactor;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 纠察事件服务。
 *
 * <p>SEC-08：事件带归属（user_id）。普通用户只能读自己产生的事件；
 * 内部/系统通道（agent 经内部 token 上报）的事件 user_id 为 NULL，
 * 全局视图仅平台审计管理员可用（由 controller 判定并留审计）。</p>
 */
@Service
@RequiredArgsConstructor
public class InspectorEventService {

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public Map<String, Object> summary(Long viewerId, boolean globalView) {
        String where = userScope(viewerId, globalView);
        String and = andScope(viewerId, globalView);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", count("SELECT COUNT(*) FROM inspector_event" + where));
        result.put("pass", count("SELECT COUNT(*) FROM inspector_event WHERE status = 'PASS'" + and));
        result.put("warning", count("SELECT COUNT(*) FROM inspector_event WHERE status IN ('WARN', 'WARNING')" + and));
        result.put("high", count("SELECT COUNT(*) FROM inspector_event WHERE severity = 'HIGH'" + and));
        result.put("critical", count("SELECT COUNT(*) FROM inspector_event WHERE severity = 'CRITICAL'" + and));
        return result;
    }

    public List<Map<String, Object>> events(int limit, Long viewerId, boolean globalView) {
        int safeLimit = Math.max(1, Math.min(limit, 200));
        String scope = scopeClause(globalView, viewerId);
        return jdbcTemplate.queryForList(
                "SELECT id, task_id AS taskId, target, status, severity, category, "
                        + "agent_claim AS agentClaim, reason, recommendation, "
                        + "requires_human AS requiresHuman, created_at AS createdAt "
                        + "FROM inspector_event" + scope + " ORDER BY created_at DESC LIMIT ?",
                safeLimit
        );
    }

    public Map<String, Object> event(String id, Long viewerId, boolean globalView) {
        String scope = scopeClause(globalView, viewerId);
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT id, task_id AS taskId, target, status, severity, category, "
                        + "agent_claim AS agentClaim, reason, recommendation, "
                        + "requires_human AS requiresHuman, metadata_json AS metadata, "
                        + "created_at AS createdAt FROM inspector_event" + scope + " AND id = ?",
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

    /** 内部/系统通道上报：事件无归属用户（NULL），普通用户读侧不可见。 */
    @Transactional
    public Map<String, Object> record(InspectionRecordRequest request) {
        return insert(request, null);
    }

    /** 登录用户主动巡检上报：事件归属当前用户。 */
    @Transactional
    public Map<String, Object> record(InspectionRecordRequest request, Long ownerId) {
        return insert(request, ownerId);
    }

    private Map<String, Object> insert(InspectionRecordRequest request, Long ownerId) {
        String id = request.getInspectionId();
        if (id == null || id.isBlank()) {
            id = "INS-" + UUID.randomUUID().toString().replace("-", "")
                    .substring(0, 12).toUpperCase();
        }

        jdbcTemplate.update(
                "INSERT INTO inspector_event "
                        + "(id, task_id, target, status, severity, category, agent_claim, "
                        + "reason, recommendation, requires_human, metadata_json, user_id, created_at) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                id, request.getTaskId(), OperationRedactor.redact(request.getTarget()), request.getStatus(),
                request.getSeverity(), request.getCategory(), OperationRedactor.redact(request.getAgentClaim()),
                OperationRedactor.redact(request.getReason()), OperationRedactor.redact(request.getRecommendation()),
                Boolean.TRUE.equals(request.getRequiresHuman()),
                json(request.getMetadata()), ownerId, LocalDateTime.now()
        );

        for (InspectionRecordRequest.Issue issue : request.getIssues()) {
            jdbcTemplate.update(
                    "INSERT INTO inspector_issue "
                            + "(event_id, category, severity, reason, recommendation) "
                            + "VALUES (?, ?, ?, ?, ?)",
                    id, issue.getCategory(), issue.getSeverity(),
                    OperationRedactor.redact(issue.getReason()), OperationRedactor.redact(issue.getRecommendation())
            );
        }

        for (InspectionRecordRequest.Evidence evidence : request.getEvidence()) {
            jdbcTemplate.update(
                    "INSERT INTO inspection_evidence "
                            + "(event_id, content, source, version, score) VALUES (?, ?, ?, ?, ?)",
                    id, OperationRedactor.redact(evidence.getContent()), evidence.getSource(),
                    evidence.getVersion(), evidence.getScore()
            );
        }

        if (request.getVerification() != null) {
            saveVerification(id, request.getVerification().getResolved(),
                    request.getVerification().getStatus(),
                    request.getVerification().getDetails());
        }
        return event(id, ownerId, ownerId == null);
    }

    @Transactional
    public Map<String, Object> verify(InspectionVerifyRequest request) {
        ensureEvent(request.getInspectionId());
        saveVerification(request.getInspectionId(), request.getResolved(),
                request.getStatus(), request.getDetails());
        return event(request.getInspectionId(), null, true);
    }

    public Map<String, Object> replan(InspectionReplanRequest request) {
        Map<String, Object> current = event(request.getInspectionId(), null, true);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("inspectionId", request.getInspectionId());
        result.put("status", "REPLANNING");
        result.put("reason", request.getReason());
        result.put("recommendation", current.get("recommendation"));
        return result;
    }

    public Map<String, Object> statistics(Long viewerId, boolean globalView) {
        String scope = scopeClause(globalView, viewerId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("summary", summary(viewerId, globalView));
        result.put("byCategory", jdbcTemplate.queryForList(
                "SELECT issue.category, COUNT(*) AS count FROM inspector_issue issue "
                        + "JOIN inspector_event event ON event.id = issue.event_id" + scope + " "
                        + "GROUP BY issue.category ORDER BY count DESC"));
        result.put("byTarget", jdbcTemplate.queryForList(
                "SELECT target, COUNT(*) AS count FROM inspector_event" + scope + " "
                        + "GROUP BY target ORDER BY count DESC"));
        return result;
    }

    /** 独立 WHERE 子句：全局/系统视图返回空串，用户视图返回完整 WHERE。 */
    private String userScope(Long viewerId, boolean globalView) {
        return globalView || viewerId == null ? "" : " WHERE user_id = " + viewerId;
    }

    /** 追加在既有 WHERE 之后的归属过滤：全局/系统视图返回空串。 */
    private String andScope(Long viewerId, boolean globalView) {
        return globalView || viewerId == null ? "" : " AND user_id = " + viewerId;
    }

    /** 查询骨架用的 WHERE 前缀（保证后续恒可拼 AND 条件）。 */
    private String scopeClause(boolean globalView, Long viewerId) {
        return globalView || viewerId == null ? " WHERE 1=1" : " WHERE user_id = " + viewerId;
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
            // SEC-11：证据/元数据同样可能夹带凭据，序列化后统一脱敏再落库。
            return OperationRedactor.redact(objectMapper.writeValueAsString(value == null ? Map.of() : value));
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
