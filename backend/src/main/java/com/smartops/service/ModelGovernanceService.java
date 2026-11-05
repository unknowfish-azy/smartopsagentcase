package com.smartops.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 平台模型治理只读清单。
 *
 * <p>只描述现有 model_gateway_* 表的元数据与近 24 小时调用计量，不读取密钥哈希、
 * 不展示完整连接串、不做额度写入或计费换算。个人 owner 隔离语义保持不变：
 * 这里给出的是平台级脱敏视图，任何写操作仍走原有个 key/group 接口。</p>
 */
@Service
public class ModelGovernanceService {
    public static final int WINDOW_HOURS = 24;

    private final JdbcTemplate jdbc;

    public ModelGovernanceService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Map<String, Object> snapshot() {
        Timestamp since = Timestamp.from(Instant.now().minusSeconds(WINDOW_HOURS * 3600L));
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("generatedAt", Instant.now().toString());
        report.put("windowHours", WINDOW_HOURS);
        report.put("timezone", "UTC");
        report.put("summary", summary(since));
        report.put("unattributed", unattributed(since));
        report.put("owners", owners(since));
        report.put("groups", groups(since));
        report.put("routes", routes());
        report.put("keys", keys());
        return report;
    }

    private Map<String, Object> summary(Timestamp since) {
        Map<String, Object> row = jdbc.query(
                "SELECT COUNT(*) AS calls, "
                        + "COALESCE(SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END),0) AS successes, "
                        + "COALESCE(SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END),0) AS failures, "
                        + "COALESCE(SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END),0) AS pending, "
                        + "COALESCE(SUM(CASE WHEN status='SUCCESS' AND total_tokens IS NULL THEN 1 ELSE 0 END),0) AS unknownUsage, "
                        + "SUM(total_tokens) AS knownTokens "
                        + "FROM model_gateway_invocation WHERE created_at>=?",
                (rs, n) -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    long calls = rs.getLong("calls");
                    long successes = rs.getLong("successes");
                    long failures = rs.getLong("failures");
                    value.put("calls", calls);
                    value.put("successes", successes);
                    value.put("failures", failures);
                    value.put("pendingCalls", rs.getLong("pending"));
                    value.put("unknownUsageCalls", rs.getLong("unknownUsage"));
                    value.put("knownTokens", rs.getObject("knownTokens", Long.class));
                    // 只统计已有明确结果的调用，避免把 PENDING 当成失败或成功。
                    value.put("successRate", successes + failures == 0 ? null : successes * 100.0 / (successes + failures));
                    return value;
                }, since).stream().findFirst().orElseGet(LinkedHashMap::new);
        return row;
    }

    private Map<String, Object> unattributed(Timestamp since) {
        return jdbc.query(
                "SELECT COUNT(*) AS calls, SUM(total_tokens) AS knownTokens FROM model_gateway_invocation "
                        + "WHERE key_id IS NULL AND created_at>=?",
                (rs, n) -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("calls", rs.getLong("calls"));
                    value.put("knownTokens", rs.getObject("knownTokens", Long.class));
                    return value;
                }, since).stream().findFirst().orElseGet(LinkedHashMap::new);
    }

    private List<Map<String, Object>> owners(Timestamp since) {
        return jdbc.query(
                "SELECT k.owner_user_id AS owner_user_id, u.username AS username, COUNT(i.id) AS calls, "
                        + "COALESCE(SUM(CASE WHEN i.status='SUCCESS' THEN 1 ELSE 0 END),0) AS successes, "
                        + "COALESCE(SUM(CASE WHEN i.status='FAILED' THEN 1 ELSE 0 END),0) AS failures, "
                        + "COALESCE(SUM(CASE WHEN i.status='PENDING' THEN 1 ELSE 0 END),0) AS pending, "
                        + "SUM(i.total_tokens) AS known_tokens, MAX(i.created_at) AS last_call_at "
                        + "FROM model_gateway_invocation i JOIN model_gateway_key k ON k.id=i.key_id "
                        + "LEFT JOIN app_user u ON u.id=k.owner_user_id "
                        + "WHERE i.created_at>=? GROUP BY k.owner_user_id, u.username ORDER BY calls DESC, k.owner_user_id",
                (rs, n) -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("ownerUserId", rs.getLong("owner_user_id"));
                    value.put("username", rs.getString("username"));
                    value.put("calls", rs.getLong("calls"));
                    value.put("successes", rs.getLong("successes"));
                    value.put("failures", rs.getLong("failures"));
                    value.put("pendingCalls", rs.getLong("pending"));
                    value.put("knownTokens", rs.getObject("known_tokens", Long.class));
                    Timestamp last = rs.getTimestamp("last_call_at");
                    value.put("lastCallAt", last == null ? null : last.toInstant().toString());
                    return value;
                }, since);
    }

    private List<Map<String, Object>> groups(Timestamp since) {
        return jdbc.query(
                "SELECT g.owner_user_id, u.username, g.slug, g.name, g.enabled, g.request_limit_24h, g.token_limit_24h, "
                        + "(SELECT COUNT(*) FROM model_gateway_invocation i WHERE i.group_slug=g.slug AND i.created_at>=?) AS calls24h, "
                        + "(SELECT SUM(i.total_tokens) FROM model_gateway_invocation i WHERE i.group_slug=g.slug AND i.created_at>=?) AS known_tokens24h, "
                        + "(SELECT COUNT(*) FROM model_gateway_route r WHERE r.group_id=g.id) AS route_count, "
                        + "(SELECT COUNT(*) FROM model_gateway_route r WHERE r.group_id=g.id AND r.enabled=TRUE "
                        + "AND (r.unhealthy_until IS NULL OR r.unhealthy_until<=CURRENT_TIMESTAMP)) AS healthy_route_count "
                        + "FROM model_gateway_group g LEFT JOIN app_user u ON u.id=g.owner_user_id "
                        + "ORDER BY g.owner_user_id, g.slug",
                (rs, n) -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("ownerUserId", rs.getObject("owner_user_id", Long.class));
                    value.put("username", rs.getString("username"));
                    value.put("slug", rs.getString("slug"));
                    value.put("name", rs.getString("name"));
                    value.put("enabled", rs.getBoolean("enabled"));
                    value.put("requestLimit24h", rs.getObject("request_limit_24h") == null ? -1L : rs.getLong("request_limit_24h"));
                    value.put("tokenLimit24h", rs.getObject("token_limit_24h") == null ? -1L : rs.getLong("token_limit_24h"));
                    value.put("calls24h", rs.getLong("calls24h"));
                    value.put("knownTokens24h", rs.getObject("known_tokens24h", Long.class));
                    value.put("routeCount", rs.getLong("route_count"));
                    value.put("healthyRouteCount", rs.getLong("healthy_route_count"));
                    return value;
                }, since, since);
    }

    private List<Map<String, Object>> routes() {
        return jdbc.query(
                "SELECT r.id, r.connection_id, r.priority, r.weight, r.enabled, r.failure_count, r.unhealthy_until, "
                        + "r.last_checked_at, r.last_error_code, g.slug AS group_slug, g.owner_user_id "
                        + "FROM model_gateway_route r JOIN model_gateway_group g ON g.id=r.group_id "
                        + "ORDER BY g.owner_user_id, g.slug, r.priority, r.weight DESC",
                (rs, n) -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("id", rs.getLong("id"));
                    value.put("ownerUserId", rs.getObject("owner_user_id", Long.class));
                    value.put("groupSlug", rs.getString("group_slug"));
                    value.put("connectionId", rs.getLong("connection_id"));
                    value.put("priority", rs.getInt("priority"));
                    value.put("weight", rs.getInt("weight"));
                    value.put("enabled", rs.getBoolean("enabled"));
                    value.put("failureCount", rs.getInt("failure_count"));
                    Timestamp unhealthy = rs.getTimestamp("unhealthy_until");
                    value.put("healthy", unhealthy == null || unhealthy.toInstant().isBefore(Instant.now()));
                    value.put("lastErrorCode", rs.getString("last_error_code"));
                    Timestamp checked = rs.getTimestamp("last_checked_at");
                    value.put("lastCheckedAt", checked == null ? null : checked.toInstant().toString());
                    return value;
                });
    }

    /** 密钥清单只给前缀与额度，不含哈希、明文或完整凭证。 */
    private List<Map<String, Object>> keys() {
        return jdbc.query(
                "SELECT k.id, k.owner_user_id, u.username, k.name, k.key_prefix, k.scope, k.expires_at, k.revoked_at, "
                        + "k.request_limit_24h, k.token_limit_24h, k.created_at "
                        + "FROM model_gateway_key k LEFT JOIN app_user u ON u.id=k.owner_user_id "
                        + "ORDER BY k.created_at DESC",
                (rs, n) -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("id", rs.getLong("id"));
                    value.put("ownerUserId", rs.getLong("owner_user_id"));
                    value.put("username", rs.getString("username"));
                    value.put("name", rs.getString("name"));
                    value.put("prefix", rs.getString("key_prefix"));
                    value.put("scope", rs.getString("scope"));
                    Timestamp expires = rs.getTimestamp("expires_at");
                    value.put("expiresAt", expires == null ? null : expires.toInstant().toString());
                    value.put("revoked", rs.getTimestamp("revoked_at") != null);
                    value.put("requestLimit24h", rs.getObject("request_limit_24h") == null ? -1L : rs.getLong("request_limit_24h"));
                    value.put("tokenLimit24h", rs.getObject("token_limit_24h") == null ? -1L : rs.getLong("token_limit_24h"));
                    Timestamp created = rs.getTimestamp("created_at");
                    value.put("createdAt", created == null ? null : created.toInstant().toString());
                    return value;
                });
    }
}
