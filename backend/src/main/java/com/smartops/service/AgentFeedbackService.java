package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Statement;
import java.time.Instant;
import java.util.List;

/**
 * Agent 执行偏好反馈（DPO 数据源）。
 *
 * 与 ChatFeedbackService 的区别：
 * - ChatFeedback 是「纠错型」：用户指出答案有误，Agent 独立复核，产出知识候选；
 * - AgentFeedback 是「偏好型」：用户对 AI 回答 / Agent 执行结果点 👍/👎，
 *   直接沉淀为 DPO 偏好对，供后续决策模型优化。
 *
 * 红线：verdict 只允许 ADOPTED / REJECTED 两态；必须带 run_id 或 step_id 才能回连轨迹。
 */
@Service
public class AgentFeedbackService {

    private final JdbcTemplate jdbc;

    public AgentFeedbackService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public AgentFeedback create(Long userId, AgentFeedbackRequest request) {
        if (request == null) throw new BusinessException(400, "AGENT_FEEDBACK_EMPTY");
        String verdict = request.verdict() == null ? "" : request.verdict().trim().toUpperCase();
        if (!"ADOPTED".equals(verdict) && !"REJECTED".equals(verdict))
            throw new BusinessException(400, "AGENT_FEEDBACK_VERDICT_INVALID");
        // 必须带 run_id 或 step_id 之一，否则无法回连轨迹
        boolean hasRunId = request.runId() != null && !request.runId().isBlank();
        boolean hasStepId = request.stepId() != null && !request.stepId().isBlank();
        if (!hasRunId && !hasStepId)
            throw new BusinessException(400, "AGENT_FEEDBACK_RUN_OR_STEP_REQUIRED");

        var keyHolder = new org.springframework.jdbc.support.GeneratedKeyHolder();
        jdbc.update(connection -> {
            var ps = connection.prepareStatement(
                    "INSERT INTO agent_feedback(request_id,run_id,step_id,verdict,reason,operator,payload_json) VALUES(?,?,?,?,?,?,?)",
                    Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, safe(request.requestId()));
            ps.setString(2, safe(request.runId()));
            ps.setString(3, safe(request.stepId()));
            ps.setString(4, verdict);
            ps.setString(5, safe(request.reason()));
            ps.setString(6, userId == null ? "anonymous" : "user:" + userId);
            // payload_json 是 JSON 列，空串会被 MySQL 拒绝（"The document is empty"），
            // 空白时写 NULL，非空时原样写入（调用方负责保证是合法 JSON）。
            String payload = request.payloadJson();
            if (payload == null || payload.isBlank()) {
                ps.setNull(7, java.sql.Types.OTHER);
            } else {
                ps.setString(7, payload);
            }
            return ps;
        }, keyHolder);
        Number generated = keyHolder.getKey();
        if (generated == null) throw new BusinessException(500, "AGENT_FEEDBACK_CREATE_FAILED");
        return detail(generated.longValue());
    }

    public AgentFeedback detail(long id) {
        var rows = jdbc.query(
                "SELECT id,request_id,run_id,step_id,verdict,reason,operator,payload_json,created_at FROM agent_feedback WHERE id=?",
                (rs, n) -> new AgentFeedback(
                        rs.getLong("id"), rs.getString("request_id"), rs.getString("run_id"),
                        rs.getString("step_id"), rs.getString("verdict"), rs.getString("reason"),
                        rs.getString("operator"), rs.getString("payload_json"),
                        rs.getTimestamp("created_at") == null ? "" : rs.getTimestamp("created_at").toInstant().toString()),
                id);
        if (rows.isEmpty()) throw new BusinessException(404, "AGENT_FEEDBACK_NOT_FOUND");
        return rows.get(0);
    }

    public List<AgentFeedback> listByRun(String runId, int limit) {
        return jdbc.query(
                "SELECT id,request_id,run_id,step_id,verdict,reason,operator,payload_json,created_at FROM agent_feedback WHERE run_id=? ORDER BY id DESC LIMIT ?",
                (rs, n) -> new AgentFeedback(
                        rs.getLong("id"), rs.getString("request_id"), rs.getString("run_id"),
                        rs.getString("step_id"), rs.getString("verdict"), rs.getString("reason"),
                        rs.getString("operator"), rs.getString("payload_json"),
                        rs.getTimestamp("created_at") == null ? "" : rs.getTimestamp("created_at").toInstant().toString()),
                runId, Math.max(1, Math.min(100, limit)));
    }

    public long countByVerdict(String verdict) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM agent_feedback WHERE verdict=?", Long.class, verdict);
    }

    private static String safe(String value) { return value == null ? "" : value; }

    public record AgentFeedbackRequest(String requestId, String runId, String stepId,
                                       String verdict, String reason, String payloadJson) {}
    public record AgentFeedback(Long id, String requestId, String runId, String stepId,
                                String verdict, String reason, String operator,
                                String payloadJson, String createdAt) {}
}
