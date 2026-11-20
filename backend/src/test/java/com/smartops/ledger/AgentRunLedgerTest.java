package com.smartops.ledger;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.TextNode;
import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.Test;

import java.sql.Timestamp;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AgentRunLedgerTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void viewParsesJsonColumnsAndTimelineFields() {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("run_id", "run_01JTEST");
        row.put("request_id", "req_01JTEST");
        row.put("intent", "restart_service");
        row.put("risk", "high");
        row.put("status", "success");
        row.put("verification_status", "verified");
        row.put("goal", "重启订单服务");
        row.put("created_at", Timestamp.valueOf("2026-11-20 10:00:00"));
        row.put("brief_json", "{\"schema\":\"smartops.security_brief.v1\",\"risk_level\":\"HIGH\"}");
        row.put("tool_calls", "[{\"toolName\":\"servers.list\",\"success\":true}]");
        row.put("approvals", null);
        row.put("result_json", "{\"verified\":true}");
        row.put("audit_event_ids", "[\"seq:1:abc123\"]");
        row.put("page_context", "{\"section\":\"sentinel\"}");

        Map<String, Object> view = AgentRunLedgerService.toView(row, mapper);

        assertEquals("run_01JTEST", view.get("runId"));
        assertEquals("HIGH", view.get("risk"));
        assertEquals("2026-11-20 10:00", view.get("createdAt"));
        assertEquals("smartops.security_brief.v1",
                ((Map<?, ?>) view.get("brief")).get("schema"));
        assertEquals("servers.list",
                ((Map<?, ?>) ((List<?>) view.get("toolCalls")).get(0)).get("toolName"));
        assertEquals("seq:1:abc123", ((List<?>) view.get("auditEventIds")).get(0));
        assertTrue(view.get("result") instanceof Map);
        assertNull(view.get("approvals"));
    }

    @Test
    void summaryTruncatesLongGoal() {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("run_id", "run_x");
        row.put("goal", "a".repeat(250));
        Map<String, Object> view = AgentRunLedgerService.toSummary(row);
        assertEquals(200, String.valueOf(view.get("goal")).length());
    }

    @Test
    void riskIsNormalized() {
        assertEquals("HIGH", AgentRunLedgerService.normalizeRisk("high"));
        assertEquals("CRITICAL", AgentRunLedgerService.normalizeRisk(" Critical "));
        assertEquals("LOW", AgentRunLedgerService.normalizeRisk("unknown"));
        assertEquals("LOW", AgentRunLedgerService.normalizeRisk(null));
    }

    @Test
    void userIdMustBeNumeric() {
        assertEquals(12L, AgentRunLedgerService.parseUserId(new TextNode("12")));
        assertNull(AgentRunLedgerService.parseUserId(new TextNode("12abc")));
        assertNull(AgentRunLedgerService.parseUserId(new TextNode("")));
        assertNull(AgentRunLedgerService.parseUserId(null));
    }

    @Test
    void recordRejectsMissingRunId() {
        AgentRunLedgerService service = new AgentRunLedgerService(null, mapper);
        BusinessException error = assertThrows(BusinessException.class,
                () -> service.record(mapper.createObjectNode()));
        assertEquals(400, error.getCode());
        assertEquals("AGENT_RUN_ID_REQUIRED", error.getMessage());
    }
}
