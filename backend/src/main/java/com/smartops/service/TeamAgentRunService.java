package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import com.smartops.security.SecurityAuditService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.List;

@Service
public class TeamAgentRunService {
    private final JdbcTemplate jdbc;
    private final TeamResourceAuthorizer authorizer;
    private final TeamAgentService agents;
    private final ObjectMapper mapper;
    private final Clock clock;
    private final SecurityAuditService audit;
    private final TeamNotificationService notifications;

    public TeamAgentRunService(JdbcTemplate jdbc, TeamResourceAuthorizer authorizer, TeamAgentService agents,
                               ObjectMapper mapper, SecurityAuditService audit) {
        this(jdbc, authorizer, agents, mapper, Clock.systemUTC(), audit, null);
    }

    @Autowired
    public TeamAgentRunService(JdbcTemplate jdbc, TeamResourceAuthorizer authorizer, TeamAgentService agents,
                               ObjectMapper mapper, SecurityAuditService audit, TeamNotificationService notifications) {
        this(jdbc, authorizer, agents, mapper, Clock.systemUTC(), audit, notifications);
    }

    TeamAgentRunService(JdbcTemplate jdbc, TeamResourceAuthorizer authorizer, TeamAgentService agents,
                        ObjectMapper mapper, Clock clock, SecurityAuditService audit) {
        this(jdbc, authorizer, agents, mapper, clock, audit, null);
    }

    TeamAgentRunService(JdbcTemplate jdbc, TeamResourceAuthorizer authorizer, TeamAgentService agents,
                        ObjectMapper mapper, Clock clock, SecurityAuditService audit, TeamNotificationService notifications) {
        this.jdbc = jdbc;
        this.authorizer = authorizer;
        this.agents = agents;
        this.mapper = mapper;
        this.clock = clock;
        this.audit = audit;
        this.notifications = notifications;
    }

    @Transactional
    public Run create(SessionUser actor, long teamId, long agentId, long versionId, String runtimeId,
                      String toolId, Map<String, String> parameters) {
        authorizer.requireMember(actor, teamId, "run");
        var agent = agents.detail(actor, teamId, agentId);
        if (agent.currentVersion() == null || agent.currentVersion().id() != versionId) {
            throw new BusinessException(409, "TEAM_AGENT_VERSION_CHANGED");
        }
        var tool = agents.availableTools(actor, teamId, agentId).stream()
                .filter(item -> item.toolId().equals(toolId)).findFirst()
                .orElseThrow(() -> new BusinessException(403, "TEAM_TOOL_NOT_ALLOWED"));
        if (runtimeId == null || runtimeId.isBlank() || runtimeId.length() > 128) throw new BusinessException(400, "TEAM_RUNTIME_INVALID");
        String json;
        try { json = mapper.writeValueAsString(parameters == null ? Map.of() : parameters); }
        catch (Exception invalid) { throw new BusinessException(400, "TEAM_TOOL_PARAMETERS_INVALID"); }
        String status = tool.readOnly() ? "APPROVED" : "PENDING_APPROVAL";
        var keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("INSERT INTO team_agent_run(team_id,agent_id,version_id,requester_id,runtime_id,tool_id,read_only,parameters_json,status,grant_expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", new String[]{"id"});
            statement.setLong(1, teamId); statement.setLong(2, agentId); statement.setLong(3, versionId);
            statement.setLong(4, actor.id()); statement.setString(5, runtimeId); statement.setString(6, toolId);
            statement.setBoolean(7, tool.readOnly()); statement.setString(8, json); statement.setString(9, status);
            if (tool.readOnly()) statement.setTimestamp(10, Timestamp.from(clock.instant().plusSeconds(300)));
            else statement.setNull(10, java.sql.Types.TIMESTAMP);
            statement.setTimestamp(11, Timestamp.from(clock.instant()));
            return statement;
        }, keys);
        Run run = require(actor, keys.getKey().longValue());
        if (notifications != null && "PENDING_APPROVAL".equals(status)) {
            jdbc.query("SELECT user_id FROM team_member WHERE team_id=? AND user_id<>? AND role IN ('owner','admin','specialist')", (row, ignored) -> row.getLong("user_id"), teamId, actor.id())
                    .forEach(userId -> notifications.notifyUser(userId, teamId, "TEAM_RUN_APPROVAL", Long.toString(run.id()), "团队有新的运行请求待审批"));
        }
        audit.record(actor, "TEAM_AGENT_RUN_CREATE", Long.toString(run.id()), "SUCCESS");
        return run;
    }

    public Run require(SessionUser actor, long runId) {
        Run run = find(runId);
        authorizer.requireMember(actor, run.teamId(), "view");
        return run;
    }

    public List<Run> list(SessionUser actor, long teamId) {
        authorizer.requireMember(actor, teamId, "view");
        return jdbc.query("SELECT * FROM team_agent_run WHERE team_id=? ORDER BY id DESC LIMIT 100", (row, ignored) -> mapRun(row), teamId);
    }

    public List<Run> pendingApprovals(SessionUser actor, long teamId) {
        authorizer.requireMember(actor, teamId, "approve");
        return jdbc.query("SELECT * FROM team_agent_run WHERE team_id=? AND status='PENDING_APPROVAL' AND requester_id<>? ORDER BY id ASC LIMIT 100",
                (row, ignored) -> mapRun(row), teamId, actor.id());
    }

    public Run requireReviewer(SessionUser actor, long runId) {
        Run run = find(runId);
        authorizer.requireMember(actor, run.teamId(), "approve");
        if (run.requesterId() == actor.id()) throw new BusinessException(403, "TEAM_RUN_SELF_APPROVAL_FORBIDDEN");
        return run;
    }

    @Transactional
    public Run markPreview(SessionUser actor, long runId, String digest) {
        Run run = requireReviewer(actor, runId);
        if (!"PENDING_APPROVAL".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_NOT_PENDING");
        if (digest == null || digest.isBlank()) throw new BusinessException(400, "TEAM_RUN_PREVIEW_INVALID");
        jdbc.update("UPDATE team_agent_run SET previewed_by=?,preview_digest=? WHERE id=? AND status='PENDING_APPROVAL'", actor.id(), digest, runId);
        return find(runId);
    }

    /**
     * 审批（兼容旧调用：不带决策依据）。
     *
     * <p>保留是为了不破坏既有调用与测试；新代码应使用带 `decisionBasis` 的重载。</p>
     */
    @Transactional
    public Run approve(SessionUser actor, long runId) {
        return approve(actor, runId, null);
    }

    /**
     * 审批并记录**决策依据**（协作优化 1）。
     *
     * <p>为什么要求依据：原实现只写 `approved_by`，事后只能回答"谁批的"，
     * 无法回答"基于什么批的"。竞赛与合规场景下，后者才是可追责的协作凭据 ——
     * 例如"依据告警 #42 的 AI 研判与预览摘要 <digest> 批准"。</p>
     *
     * <p>依据是**可选**参数，但一旦提供就会被审计记录；这比强制填写更现实：
     * 强制会让审批人写"ok"来绕过，反而失去信息量。</p>
     */
    @Transactional
    public Run approve(SessionUser actor, long runId, String decisionBasis) {
        Run run = requireReviewer(actor, runId);
        requireCurrentTool(actor, run);
        if (agents.detail(actor, run.teamId(), run.agentId()).currentVersion().id() != run.versionId()) {
            throw new BusinessException(409, "TEAM_AGENT_VERSION_CHANGED");
        }
        if (!"PENDING_APPROVAL".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_NOT_PENDING");
        if (run.previewedBy() == null || run.previewedBy() != actor.id()) {
            throw new BusinessException(409, "TEAM_RUN_PREVIEW_REQUIRED");
        }
        String basis = normalizeBasis(decisionBasis);
        String token = UUID.randomUUID().toString();
        int changed = jdbc.update("""
                UPDATE team_agent_run SET status='APPROVED',approved_by=?,grant_token=?,grant_expires_at=?,decision_basis=?
                 WHERE id=? AND status='PENDING_APPROVAL'
                """, actor.id(), token, Timestamp.from(clock.instant().plusSeconds(300)), basis, runId);
        if (changed != 1) throw new BusinessException(409, "TEAM_RUN_NOT_PENDING");
        audit.record(actor, "TEAM_AGENT_RUN_APPROVE", Long.toString(runId), "SUCCESS",
                basis == null ? null : truncateForAudit(basis));
        return find(runId);
    }

    /** 审计明细只保留前 200 字符，完整依据在 run 行里。 */
    private static String truncateForAudit(String basis) {
        return basis.length() <= 200 ? basis : basis.substring(0, 200);
    }

    /** 决策依据只做长度约束与去除控制字符，不评判内容好坏。 */
    private static String normalizeBasis(String value) {
        if (value == null || value.isBlank()) return null;
        String text = value.replaceAll("[\\p{Cntrl}&&[^\\n\\t]]", "").trim();
        if (text.isEmpty()) return null;
        return text.length() <= 800 ? text : text.substring(0, 800);
    }

    @Transactional
    public Run consumeGrant(SessionUser actor, long runId, String commandDigest) {
        Run run = find(runId);
        authorizer.requireMember(actor, run.teamId(), "run");
        if (run.requesterId() != actor.id()) throw new BusinessException(403, "TEAM_RUN_REQUESTER_REQUIRED");
        requireCurrentTool(actor, run);
        if (agents.detail(actor, run.teamId(), run.agentId()).currentVersion().id() != run.versionId()) {
            throw new BusinessException(409, "TEAM_AGENT_VERSION_CHANGED");
        }
        if ("PENDING_APPROVAL".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_APPROVAL_REQUIRED");
        if (!"APPROVED".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_GRANT_USED");
        if (!run.readOnly() && !java.util.Objects.equals(run.previewDigest(), commandDigest)) {
            throw new BusinessException(409, "TEAM_RUN_PREVIEW_CHANGED");
        }
        if (run.grantExpiresAt() == null || !run.grantExpiresAt().isAfter(clock.instant())) {
            throw new BusinessException(403, "TEAM_RUN_GRANT_INVALID");
        }
        int changed = jdbc.update("UPDATE team_agent_run SET status='RUNNING',grant_token=NULL WHERE id=? AND status='APPROVED'",
                runId);
        if (changed != 1) throw new BusinessException(409, "TEAM_RUN_GRANT_USED");
        audit.record(actor, "TEAM_AGENT_RUN_EXECUTE", Long.toString(runId), "SUCCESS");
        return find(runId);
    }

    @Transactional
    public Run finish(SessionUser actor, long runId, String status) {
        Run run = find(runId);
        if (run.requesterId() != actor.id() || !"RUNNING".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_NOT_RUNNING");
        if (!"SUCCEEDED".equals(status) && !"FAILED".equals(status)) throw new BusinessException(400, "TEAM_RUN_STATUS_INVALID");
        jdbc.update("UPDATE team_agent_run SET status=? WHERE id=? AND status='RUNNING'", status, runId);
        audit.record(actor, "TEAM_AGENT_RUN_FINISH", Long.toString(runId), "SUCCEEDED".equals(status) ? "SUCCESS" : "FAILURE");
        return find(runId);
    }

    private Run find(long runId) {
        return jdbc.query("SELECT * FROM team_agent_run WHERE id=?", (row, ignored) -> mapRun(row), runId)
                .stream().findFirst().orElseThrow(() -> new BusinessException(404, "TEAM_RUN_NOT_FOUND"));
    }

    private OperationToolService.ToolDescriptor requireCurrentTool(SessionUser actor, Run run) {
        return agents.availableTools(actor, run.teamId(), run.agentId()).stream()
                .filter(tool -> tool.toolId().equals(run.toolId()) && tool.readOnly() == run.readOnly()).findFirst()
                .orElseThrow(() -> new BusinessException(403, "TEAM_TOOL_NOT_ALLOWED"));
    }

    private Run mapRun(java.sql.ResultSet row) throws java.sql.SQLException {
        return new Run(
                row.getLong("id"), row.getLong("team_id"), row.getLong("agent_id"), row.getLong("version_id"),
                row.getLong("requester_id"), row.getString("runtime_id"), row.getString("tool_id"), row.getBoolean("read_only"),
                row.getString("parameters_json"), row.getString("status"), row.getObject("previewed_by", Long.class), row.getString("preview_digest"), row.getObject("approved_by", Long.class),
                row.getString("grant_token"), row.getTimestamp("grant_expires_at") == null ? null : row.getTimestamp("grant_expires_at").toInstant(),
                columnOrNull(row, "decision_basis"), instantOrNull(row, "created_at"));
    }

    /** 列可能尚未添加（旧库），读不到时返回 null 而不是让整个查询失败。 */
    private static String columnOrNull(java.sql.ResultSet row, String column) {
        try {
            return row.getString(column);
        } catch (java.sql.SQLException missing) {
            return null;
        }
    }

    /** 兼容旧库缺列：提交时间只用于展示，读不到时返回 null。 */
    private static String instantOrNull(java.sql.ResultSet row, String column) {
        try {
            var value = row.getTimestamp(column);
            return value == null ? null : value.toInstant().toString();
        } catch (java.sql.SQLException missing) {
            return null;
        }
    }

    public record Run(long id, long teamId, long agentId, long versionId, long requesterId, String runtimeId,
                      String toolId, boolean readOnly, @JsonIgnore String parametersJson, String status, Long previewedBy,
                      @JsonIgnore String previewDigest, Long approvedBy,
                      @JsonIgnore String grantToken, Instant grantExpiresAt,
                      String decisionBasis, String createdAt) {}
}
