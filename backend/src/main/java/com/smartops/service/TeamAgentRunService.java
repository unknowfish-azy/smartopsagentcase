package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import com.smartops.security.SecurityAuditService;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.List;

@Service
public class TeamAgentRunService {
    private final JdbcTemplate jdbc;
    private final TeamResourceAuthorizer authorizer;
    private final TeamAgentService agents;
    private final ObjectMapper mapper;
    /** 仅用于绑定摘要：键序固定，保证同样的参数得到同样的摘要。 */
    private final ObjectMapper canonicalMapper;
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
        this.canonicalMapper = mapper.copy().configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
        this.clock = clock;
        this.audit = audit;
        this.notifications = notifications;
    }

    @Transactional
    public Run create(SessionUser actor, long teamId, long agentId, long versionId, String runtimeId,
                      String toolId, Map<String, String> parameters) {
        return create(actor, teamId, agentId, versionId, runtimeId, toolId, parameters, null);
    }

    /**
     * 创建运行请求，可选幂等键（SEC-05）。
     *
     * <p>同一申请人重复提交同一 `idempotencyKey` 时返回既有运行，避免重复请求堆出多条待审记录；
     * 并发窗口由 `(team_id, requester_id, idempotency_key)` 唯一索引兜住。</p>
     */
    @Transactional
    public Run create(SessionUser actor, long teamId, long agentId, long versionId, String runtimeId,
                      String toolId, Map<String, String> parameters, String idempotencyKey) {
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
        String key = normalizeIdempotencyKey(idempotencyKey);
        if (key != null) {
            Run existing = findByIdempotencyKey(teamId, actor.id(), key);
            if (existing != null) return existing;
        }
        String status = tool.readOnly() ? "APPROVED" : "PENDING_APPROVAL";
        // SEC-05：只读运行同样持有一次性 grant_token，执行时统一校验，避免"只读即可不带凭据"的旁路。
        String grantToken = UUID.randomUUID().toString();
        var keys = new GeneratedKeyHolder();
        try {
            jdbc.update(connection -> {
                var statement = connection.prepareStatement("INSERT INTO team_agent_run(team_id,agent_id,version_id,requester_id,runtime_id,tool_id,read_only,parameters_json,status,grant_token,grant_expires_at,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", new String[]{"id"});
                statement.setLong(1, teamId); statement.setLong(2, agentId); statement.setLong(3, versionId);
                statement.setLong(4, actor.id()); statement.setString(5, runtimeId); statement.setString(6, toolId);
                statement.setBoolean(7, tool.readOnly()); statement.setString(8, json); statement.setString(9, status);
                if (tool.readOnly()) {
                    statement.setString(10, grantToken);
                    statement.setTimestamp(11, Timestamp.from(clock.instant().plusSeconds(300)));
                } else {
                    statement.setNull(10, java.sql.Types.VARCHAR);
                    statement.setNull(11, java.sql.Types.TIMESTAMP);
                }
                if (key == null) statement.setNull(12, java.sql.Types.VARCHAR); else statement.setString(12, key);
                statement.setTimestamp(13, Timestamp.from(clock.instant()));
                return statement;
            }, keys);
        } catch (DuplicateKeyException duplicate) {
            // 并发提交同一幂等键：唯一索引先命中，返回先落库的那条。
            Run existing = key == null ? null : findByIdempotencyKey(teamId, actor.id(), key);
            if (existing == null) throw duplicate;
            return existing;
        }
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
        var tool = requireCurrentTool(actor, run);
        if (agents.detail(actor, run.teamId(), run.agentId()).currentVersion().id() != run.versionId()) {
            throw new BusinessException(409, "TEAM_AGENT_VERSION_CHANGED");
        }
        if (!"PENDING_APPROVAL".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_NOT_PENDING");
        // SEC-05：Long 引用比较在 user id > 127 时会误判，必须用值比较。
        if (run.previewedBy() == null || !Objects.equals(run.previewedBy(), actor.id())) {
            throw new BusinessException(409, "TEAM_RUN_PREVIEW_REQUIRED");
        }
        String basis = normalizeBasis(decisionBasis);
        String token = UUID.randomUUID().toString();
        // SEC-05：绑定摘要纳入规范化参数、工具标识与工具版本、审批人，
        // 证明"批准的就是将要执行的那一份"，而不是只看渲染后的命令文本。
        String digest = bindingDigest(run.toolId(), tool.version(), actor.id(), run.parametersJson());
        int changed = jdbc.update("""
                UPDATE team_agent_run SET status='APPROVED',approved_by=?,grant_token=?,grant_expires_at=?,decision_basis=?,grant_digest=?
                 WHERE id=? AND status='PENDING_APPROVAL'
                """, actor.id(), token, Timestamp.from(clock.instant().plusSeconds(300)), basis, digest, runId);
        if (changed != 1) throw new BusinessException(409, "TEAM_RUN_NOT_PENDING");
        String auditDetail = "digest=" + digest + (basis == null ? "" : "; basis=" + truncateForAudit(basis));
        audit.record(actor, "TEAM_AGENT_RUN_APPROVE", Long.toString(runId), "SUCCESS", auditDetail);
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

    /**
     * 消费 grant 并原子地切换到 RUNNING（SEC-05）。
     *
     * <p>三层校验：① grant_token 必须携带且与库中一致（常量时间比较）；
     * ② 渲染命令摘要与预览时一致（防渲染漂移）；
     * ③ 服务端绑定摘要按「参数 + 工具 + 工具版本 + 审批人」重算一致（防参数被改）。
     * 条件 UPDATE 仍是唯一的一次性消费点，不得改为先查后改。</p>
     */
    @Transactional
    public Run consumeGrant(SessionUser actor, long runId, String commandDigest, String grantToken) {
        Run run = find(runId);
        authorizer.requireMember(actor, run.teamId(), "run");
        if (!Objects.equals(run.requesterId(), actor.id())) throw new BusinessException(403, "TEAM_RUN_REQUESTER_REQUIRED");
        var tool = requireCurrentTool(actor, run);
        if (agents.detail(actor, run.teamId(), run.agentId()).currentVersion().id() != run.versionId()) {
            throw new BusinessException(409, "TEAM_AGENT_VERSION_CHANGED");
        }
        if ("PENDING_APPROVAL".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_APPROVAL_REQUIRED");
        if ("CANCELED".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_CANCELED");
        if (!"APPROVED".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_GRANT_USED");
        if (grantToken == null || grantToken.isBlank()) throw new BusinessException(409, "TEAM_RUN_GRANT_TOKEN_REQUIRED");
        if (!constantTimeEquals(run.grantToken(), grantToken)) {
            throw new BusinessException(403, "TEAM_RUN_GRANT_TOKEN_MISMATCH");
        }
        if (!run.readOnly()) {
            if (!Objects.equals(run.previewDigest(), commandDigest)) {
                throw new BusinessException(409, "TEAM_RUN_PREVIEW_CHANGED");
            }
            String expected = bindingDigest(run.toolId(), tool.version(), run.approvedBy(), run.parametersJson());
            if (!Objects.equals(run.grantDigest(), expected)) {
                throw new BusinessException(409, "TEAM_RUN_PREVIEW_CHANGED");
            }
        }
        if (run.grantExpiresAt() == null || !run.grantExpiresAt().isAfter(clock.instant())) {
            throw new BusinessException(403, "TEAM_RUN_GRANT_INVALID");
        }
        int changed = jdbc.update("UPDATE team_agent_run SET status='RUNNING',grant_token=NULL WHERE id=? AND status='APPROVED' AND grant_token=?",
                runId, grantToken);
        if (changed != 1) throw new BusinessException(409, "TEAM_RUN_GRANT_USED");
        audit.record(actor, "TEAM_AGENT_RUN_EXECUTE", Long.toString(runId), "SUCCESS", run.grantDigest() == null ? null : "digest=" + run.grantDigest());
        return find(runId);
    }

    /**
     * 撤回审批（SEC-05）：待审或已批运行都可取消，取消后 grant_token 立即作废。
     *
     * <p>申请人可自行撤回；其他成员需要具备审批权（approve），避免任意成员打断他人运行。</p>
     */
    @Transactional
    public Run cancel(SessionUser actor, long runId, String reason) {
        Run run = find(runId);
        authorizer.requireMember(actor, run.teamId(), "view");
        if (!Objects.equals(run.requesterId(), actor.id())) authorizer.requireMember(actor, run.teamId(), "approve");
        if (!"PENDING_APPROVAL".equals(run.status()) && !"APPROVED".equals(run.status())) {
            throw new BusinessException(409, "TEAM_RUN_NOT_CANCELABLE");
        }
        String text = normalizeCancelReason(reason);
        int changed = jdbc.update("""
                UPDATE team_agent_run SET status='CANCELED',grant_token=NULL,grant_digest=NULL,canceled_by=?,canceled_at=?,cancel_reason=?
                 WHERE id=? AND status IN ('PENDING_APPROVAL','APPROVED')
                """, actor.id(), Timestamp.from(clock.instant()), text, runId);
        if (changed != 1) throw new BusinessException(409, "TEAM_RUN_NOT_CANCELABLE");
        audit.record(actor, "TEAM_AGENT_RUN_CANCEL", Long.toString(runId), "SUCCESS",
                text == null ? null : truncateForAudit(text));
        return find(runId);
    }

    /** 撤回理由只做长度约束与去除控制字符。 */
    private static String normalizeCancelReason(String value) {
        if (value == null || value.isBlank()) return null;
        String text = value.replaceAll("[\\p{Cntrl}&&[^\\n\\t]]", "").trim();
        if (text.isEmpty()) return null;
        return text.length() <= 400 ? text : text.substring(0, 400);
    }

    /** 幂等键只允许可打印短串；超长或空白视为未提供（未提供时不参与去重）。 */
    private static String normalizeIdempotencyKey(String value) {
        if (value == null || value.isBlank()) return null;
        String text = value.replaceAll("[\\p{Cntrl}]", "").trim();
        if (text.isEmpty()) return null;
        return text.length() <= 128 ? text : null;
    }

    private Run findByIdempotencyKey(long teamId, long requesterId, String key) {
        return jdbc.query("SELECT * FROM team_agent_run WHERE team_id=? AND requester_id=? AND idempotency_key=? ORDER BY id DESC LIMIT 1",
                (row, ignored) -> mapRun(row), teamId, requesterId, key).stream().findFirst().orElse(null);
    }

    /**
     * 审批绑定摘要：`v1 + toolId + 工具版本 + 审批人 + 规范化参数`。
     *
     * <p>参数按键序重新序列化，避免同样内容因键顺序不同产生不同摘要。</p>
     */
    private String bindingDigest(String toolId, String toolVersion, Long approverId, String parametersJson) {
        String canonical;
        try {
            canonical = canonicalMapper.writeValueAsString(canonicalMapper.readTree(parametersJson == null ? "{}" : parametersJson));
        } catch (Exception invalid) {
            throw new BusinessException(400, "TEAM_TOOL_PARAMETERS_INVALID");
        }
        String material = "v1\n" + toolId + "\n" + toolVersion + "\n" + approverId + "\n" + canonical;
        try {
            return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(material.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static boolean constantTimeEquals(String expected, String provided) {
        if (expected == null || provided == null) return false;
        return MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8), provided.getBytes(StandardCharsets.UTF_8));
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
                columnOrNull(row, "decision_basis"), instantOrNull(row, "created_at"),
                columnOrNull(row, "grant_digest"), row.getObject("canceled_by", Long.class),
                instantOrNull(row, "canceled_at"), columnOrNull(row, "cancel_reason"));
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
                      String decisionBasis, String createdAt,
                      @JsonIgnore String grantDigest, Long canceledBy, String canceledAt, String cancelReason) {}
}
