package com.smartops.service;

import com.smartops.config.BusinessSchemaHealthIndicator;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 管理总览的治理待办聚合。
 *
 * <p>只由已有权威数据组成：团队待审批运行（团队批准资格）、近 24 小时失败/拒绝审计
 * （admin.audit）、缺失表检查（管理端接入检查能力）、待首次改密账户（admin.users）。
 * 没有对应能力就不返回该项，也不返回伪造的 0 值统计。</p>
 */
@Service
public class AdminWorkbenchService {
    private static final int APPROVAL_SAMPLE_LIMIT = 5;

    private final JdbcTemplate jdbc;
    private final UserAccountService accounts;
    private final BusinessSchemaHealthIndicator schema;

    public AdminWorkbenchService(JdbcTemplate jdbc, UserAccountService accounts, BusinessSchemaHealthIndicator schema) {
        this.jdbc = jdbc;
        this.accounts = accounts;
        this.schema = schema;
    }

    public Map<String, Object> workbench(SessionUser actor) {
        List<Map<String, Object>> items = new ArrayList<>();
        if (actor != null) {
            approvals(actor).ifPresent(items::add);
            if (accounts.hasPlatformCapability(actor, "admin.audit")) auditAttention().ifPresent(items::add);
            if (hasReadinessCapability(actor)) readinessGap().ifPresent(items::add);
            if (accounts.hasPlatformCapability(actor, "admin.users")) passwordChanges().ifPresent(items::add);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("generatedAt", Instant.now().toString());
        result.put("items", items);
        return result;
    }

    /** 与 AdminReadinessController 同一能力集合：能看接入检查页的人才能看到该缺口。 */
    private boolean hasReadinessCapability(SessionUser actor) {
        return accounts.hasPlatformCapability(actor, "admin.config")
                || accounts.hasPlatformCapability(actor, "admin.security")
                || accounts.hasPlatformCapability(actor, "admin.users");
    }

    private java.util.Optional<Map<String, Object>> approvals(SessionUser actor) {
        String where = " WHERE r.status='PENDING_APPROVAL' AND r.requester_id<>? AND t.status='active' "
                + "AND (m.role IN ('owner','admin') OR (m.role='specialist' AND EXISTS("
                + "SELECT 1 FROM team_member_capability c WHERE c.team_id=r.team_id AND c.user_id=? AND c.capability='approve')))";
        long count = jdbc.queryForObject("SELECT COUNT(*) FROM team_agent_run r "
                + "JOIN team_workspace t ON t.id=r.team_id "
                + "JOIN team_member m ON m.team_id=r.team_id AND m.user_id=?" + where,
                Long.class, actor.id(), actor.id(), actor.id());
        if (count <= 0) return java.util.Optional.empty();
        List<Map<String, Object>> samples = jdbc.query("SELECT r.id, r.team_id, t.name AS team_name, r.tool_id, r.created_at "
                + "FROM team_agent_run r JOIN team_workspace t ON t.id=r.team_id "
                + "JOIN team_member m ON m.team_id=r.team_id AND m.user_id=?" + where + " ORDER BY r.id ASC LIMIT ?",
                (rs, n) -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("runId", rs.getLong("id"));
                    value.put("teamId", rs.getLong("team_id"));
                    value.put("teamName", rs.getString("team_name"));
                    value.put("toolId", rs.getString("tool_id"));
                    Timestamp created = rs.getTimestamp("created_at");
                    value.put("createdAt", created == null ? null : created.toInstant().toString());
                    return value;
                }, actor.id(), actor.id(), actor.id(), APPROVAL_SAMPLE_LIMIT);
        return java.util.Optional.of(item("APPROVALS", "待审批的 Agent 运行",
                "你具备批准资格的团队中有待处理运行；只能看到这些团队的元数据。",
                count, "team_agent_run", samples, "/admin/approvals", null));
    }

    private java.util.Optional<Map<String, Object>> auditAttention() {
        Timestamp since = Timestamp.from(Instant.now().minusSeconds(24 * 3600L));
        Map<String, Object> row = jdbc.query("SELECT COUNT(*) AS total, MAX(created_at) AS latest "
                        + "FROM security_audit_event WHERE outcome IN ('FAILURE','DENIED') AND created_at>=?",
                (rs, n) -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("total", rs.getLong("total"));
                    Timestamp latest = rs.getTimestamp("latest");
                    value.put("latest", latest == null ? null : latest.toInstant().toString());
                    return value;
                }, since).stream().findFirst().orElseGet(LinkedHashMap::new);
        long total = row.get("total") instanceof Number number ? number.longValue() : 0L;
        if (total <= 0) return java.util.Optional.empty();
        Map<String, Object> entry = item("AUDIT_ATTENTION", "近 24 小时失败或拒绝的安全事件",
                "来自审计账，按结果字段统计；依据详情见审计记录。",
                total, "security_audit_event", List.of(), "/admin/audit?outcome=DENIED", (String) row.get("latest"));
        return java.util.Optional.of(entry);
    }

    private java.util.Optional<Map<String, Object>> readinessGap() {
        List<String> missing = schema.missingTables();
        if (missing == null || missing.isEmpty()) return java.util.Optional.empty();
        return java.util.Optional.of(item("READINESS_GAP", "数据库结构缺口",
                "服务端检查发现缺失的业务表；这不是连通性结论，需按接入检查页指引处理。",
                missing.size(), "business_schema", missing.stream().limit(5).map(name -> Map.<String, Object>of("table", name)).toList(),
                "/admin/readiness", null));
    }

    private java.util.Optional<Map<String, Object>> passwordChanges() {
        Map<String, Long> overview = accounts.overview();
        Object raw = overview == null ? null : overview.get("pendingPasswordChanges");
        long total = raw instanceof Number number ? number.longValue() : 0L;
        if (total <= 0) return java.util.Optional.empty();
        return java.util.Optional.of(item("PASSWORD_CHANGES", "待首次改密账户",
                "由账户统计得出；目标账户在改密前不能发起业务请求。",
                total, "app_user", List.of(), "/admin/users", null));
    }

    private Map<String, Object> item(String type, String label, String detail, long count, String source,
            List<Map<String, Object>> samples, String link, String observedAt) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("type", type);
        value.put("label", label);
        value.put("detail", detail);
        value.put("count", count);
        value.put("source", source);
        value.put("observedAt", observedAt == null ? Instant.now().toString() : observedAt);
        value.put("link", link);
        if (!samples.isEmpty()) value.put("samples", samples);
        return value;
    }
}
