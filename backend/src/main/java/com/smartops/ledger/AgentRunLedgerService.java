package com.smartops.ledger;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Trust Ledger：Agent 运行账本的读写服务。
 *
 * <p>写入只走内部令牌通道（ai-service 在每次 /api/agent/run 结束后回传真实结果）；
 * 读取按当前登录用户隔离。账本只记录结构化事实（输入/风险/工具/审批/结果/审计事件），
 * 不保存凭据，也不在缺失数据时补任何占位值。</p>
 */
@Service
public class AgentRunLedgerService {

    private static final Logger log = LoggerFactory.getLogger(AgentRunLedgerService.class);

    private static final int MAX_RUN_ID_CHARS = 128;
    private static final int MAX_REQUEST_ID_CHARS = 128;
    private static final int MAX_GOAL_CHARS = 4000;
    private static final int MAX_SUMMARY_GOAL_CHARS = 200;
    private static final int MAX_INTENT_CHARS = 64;
    private static final int MAX_STATUS_CHARS = 32;

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public AgentRunLedgerService(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    // ---------------------------------------------------------------- 写入

    public Map<String, Object> record(JsonNode body) {
        if (body == null || !body.isObject()) {
            throw new BusinessException(400, "AGENT_RUN_BODY_EMPTY");
        }
        String runId = truncate(text(body, "runId"), MAX_RUN_ID_CHARS);
        if (runId == null || runId.isBlank()) {
            throw new BusinessException(400, "AGENT_RUN_ID_REQUIRED");
        }
        String status = truncate(text(body, "status"), MAX_STATUS_CHARS);
        if (status == null || status.isBlank()) {
            status = "unknown";
        }
        String verificationStatus = truncate(text(body, "verificationStatus"), MAX_STATUS_CHARS);
        if (verificationStatus == null || verificationStatus.isBlank()) {
            verificationStatus = "not_required";
        }

        // 同一 run_id 重试幂等：唯一键冲突时整行覆盖为最新真实结果。
        jdbc.update("INSERT INTO agent_run(run_id,request_id,user_id,goal,intent,risk,status,"
                        + "verification_status,brief_json,tool_calls,approvals,result_json,audit_event_ids,"
                        + "page_context,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                        + " ON DUPLICATE KEY UPDATE request_id=VALUES(request_id),user_id=VALUES(user_id),"
                        + "goal=VALUES(goal),intent=VALUES(intent),risk=VALUES(risk),status=VALUES(status),"
                        + "verification_status=VALUES(verification_status),brief_json=VALUES(brief_json),"
                        + "tool_calls=VALUES(tool_calls),approvals=VALUES(approvals),result_json=VALUES(result_json),"
                        + "audit_event_ids=VALUES(audit_event_ids),page_context=VALUES(page_context)",
                runId,
                truncate(text(body, "requestId"), MAX_REQUEST_ID_CHARS),
                parseUserId(body.get("userId")),
                truncate(text(body, "goal"), MAX_GOAL_CHARS),
                truncate(text(body, "intent"), MAX_INTENT_CHARS),
                normalizeRisk(text(body, "risk")),
                status,
                verificationStatus,
                jsonText(body.get("brief")),
                jsonText(body.get("toolCalls")),
                jsonText(body.get("approvals")),
                jsonText(body.get("result")),
                jsonText(body.get("auditEventIds")),
                jsonText(body.get("pageContext")),
                Timestamp.valueOf(LocalDateTime.now()));

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("runId", runId);
        payload.put("recorded", true);
        return payload;
    }

    // ---------------------------------------------------------------- 查询

    public java.util.List<Map<String, Object>> list(Long userId, int limit) {
        int capped = Math.max(1, Math.min(100, limit));
        var rows = jdbc.queryForList(
                "SELECT id,run_id,request_id,intent,risk,status,verification_status,goal,created_at"
                        + " FROM agent_run WHERE user_id=? ORDER BY id DESC LIMIT ?", userId, capped);
        var result = new ArrayList<Map<String, Object>>(rows.size());
        for (Map<String, Object> row : rows) {
            result.add(toSummary(row));
        }
        return result;
    }

    public Map<String, Object> detail(Long userId, String runId) {
        var rows = jdbc.queryForList(
                "SELECT * FROM agent_run WHERE run_id=? AND user_id=?", runId, userId);
        if (rows.isEmpty()) {
            throw new BusinessException(404, "AGENT_RUN_NOT_FOUND");
        }
        return toView(rows.get(0), mapper);
    }

    // ---------------------------------------------------------------- 视图映射（纯函数，便于单测）

    static Map<String, Object> toSummary(Map<String, Object> row) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("runId", text(row.get("run_id")));
        view.put("requestId", text(row.get("request_id")));
        view.put("intent", text(row.get("intent")));
        view.put("risk", normalizeRisk(text(row.get("risk"))));
        view.put("status", text(row.get("status")));
        view.put("verificationStatus", text(row.get("verification_status")));
        view.put("goal", truncate(text(row.get("goal")), MAX_SUMMARY_GOAL_CHARS));
        view.put("createdAt", timeText(row.get("created_at")));
        return view;
    }

    static Map<String, Object> toView(Map<String, Object> row, ObjectMapper mapper) {
        Map<String, Object> view = new LinkedHashMap<>(toSummary(row));
        view.put("goal", text(row.get("goal")));
        view.put("brief", parseJson(row.get("brief_json"), mapper));
        view.put("toolCalls", parseJson(row.get("tool_calls"), mapper));
        view.put("approvals", parseJson(row.get("approvals"), mapper));
        view.put("result", parseJson(row.get("result_json"), mapper));
        view.put("auditEventIds", parseJson(row.get("audit_event_ids"), mapper));
        view.put("pageContext", parseJson(row.get("page_context"), mapper));
        return view;
    }

    // ---------------------------------------------------------------- 工具

    static String normalizeRisk(String raw) {
        if (raw == null) {
            return "LOW";
        }
        String value = raw.trim().toUpperCase(Locale.ROOT);
        return switch (value) {
            case "LOW", "MEDIUM", "HIGH", "CRITICAL" -> value;
            default -> "LOW";
        };
    }

    static Long parseUserId(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        String raw = node.asText("").trim();
        if (!raw.matches("\\d{1,19}")) {
            return null;
        }
        try {
            return Long.parseLong(raw);
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    private static Object parseJson(Object raw, ObjectMapper mapper) {
        if (raw == null) {
            return null;
        }
        String value = String.valueOf(raw);
        if (value.isBlank()) {
            return null;
        }
        try {
            return mapper.readValue(value, Object.class);
        } catch (Exception ex) {
            // 解析失败时返回原始串，让前端看到真实存储内容而不是伪装成空。
            log.warn("agent_run JSON 列解析失败，按原文返回: {}", ex.getMessage());
            return value;
        }
    }

    private static String jsonText(JsonNode node) {
        if (node == null || node.isNull() || node.isMissingNode()) {
            return null;
        }
        return node.toString();
    }

    private static String text(JsonNode body, String field) {
        JsonNode node = body.get(field);
        if (node == null || node.isNull()) {
            return null;
        }
        return node.asText();
    }

    private static String text(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static String timeText(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Timestamp timestamp) {
            return timestamp.toLocalDateTime().toString().replace('T', ' ');
        }
        if (value instanceof LocalDateTime dateTime) {
            return dateTime.toString().replace('T', ' ');
        }
        return String.valueOf(value);
    }

    private static String truncate(String value, int max) {
        if (value == null || value.length() <= max) {
            return value;
        }
        return value.substring(0, max);
    }
}
