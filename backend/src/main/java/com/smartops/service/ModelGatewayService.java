package com.smartops.service;

import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class ModelGatewayService {
    private final JdbcTemplate jdbc;
    private final ModelConnectionService connections;
    private final SecureRandom random = new SecureRandom();

    public record IssuedKey(Long id, String name, String key, String prefix, String scope, Instant expiresAt) {}
    public record GatewayPrincipal(Long id, Long ownerUserId, String scope) {}

    @Transactional
    public IssuedKey issueKey(Long ownerUserId, String name, String scope, Instant expiresAt) {
        if (ownerUserId == null || name == null || name.isBlank() || name.length() > 120) throw new BusinessException(400, "Invalid key name");
        if (scope != null && !"PERSONAL".equals(scope)) throw new BusinessException(400, "Only PERSONAL keys are supported");
        if (expiresAt != null && !expiresAt.isAfter(Instant.now())) throw new BusinessException(400, "Expiry must be in the future");
        String raw = "sk-smartops-" + randomPart(32);
        long id = nextId();
        String prefix = raw.substring(0, Math.min(raw.length(), 20));
        jdbc.update("INSERT INTO model_gateway_key(id,owner_user_id,name,key_prefix,key_hash,scope,expires_at) VALUES(?,?,?,?,?,?,?)",
                id, ownerUserId, name.trim(), prefix, hash(raw), scope == null ? "PERSONAL" : scope, expiresAt == null ? null : java.sql.Timestamp.from(expiresAt));
        return new IssuedKey(id, name.trim(), raw, prefix, scope == null ? "PERSONAL" : scope, expiresAt);
    }

    public GatewayPrincipal authenticate(String raw) {
        if (raw == null || !raw.matches("sk-smartops-[a-f0-9]{64}")) throw new BusinessException(401, "Invalid gateway key");
        List<GatewayPrincipal> rows = jdbc.query("SELECT id,owner_user_id,scope,expires_at FROM model_gateway_key WHERE key_hash=? AND revoked_at IS NULL", (rs, n) -> {
            var expires = rs.getTimestamp("expires_at");
            if (expires != null && !expires.toInstant().isAfter(Instant.now())) return null;
            if (!"PERSONAL".equals(rs.getString("scope"))) return null;
            return new GatewayPrincipal(rs.getLong("id"), rs.getLong("owner_user_id"), rs.getString("scope"));
        }, hash(raw)).stream().filter(java.util.Objects::nonNull).toList();
        if (rows.isEmpty()) throw new BusinessException(401, "Invalid or expired gateway key");
        return rows.get(0);
    }

    public ModelInvocationResponse invoke(GatewayPrincipal principal, String group, ModelInvocationRequest request) {
        if (group == null || !group.matches("[a-zA-Z0-9._-]{1,120}")) throw new BusinessException(400, "Invalid model group");
        if (!"PERSONAL".equals(principal.scope())) throw new BusinessException(403, "Key scope not supported");
        enforceQuota(principal.id(), principal.ownerUserId(), group);
        List<Map<String, Long>> routes = jdbc.query("SELECT r.id,r.connection_id FROM model_gateway_group g JOIN model_gateway_route r ON r.group_id=g.id WHERE g.slug=? AND g.scope='PERSONAL' AND g.owner_user_id=? AND g.enabled=TRUE AND r.enabled=TRUE AND (r.unhealthy_until IS NULL OR r.unhealthy_until <= CURRENT_TIMESTAMP) ORDER BY r.priority ASC, r.weight DESC", (rs, n) -> Map.of("routeId", rs.getLong("id"), "connectionId", rs.getLong("connection_id")), group, principal.ownerUserId());
        if (routes.isEmpty()) throw new BusinessException(404, "Model group unavailable");
        long started = System.nanoTime();
        RuntimeException lastFailure = null;
        for (Map<String, Long> route : routes) {
            Long connectionId = route.get("connectionId");
            try {
                var result = connections.invoke(principal.ownerUserId(), connectionId, request);
                markRouteSuccess(route.get("routeId"));
                recordSafely(principal.id(), group, result.getModel(), "SUCCESS", elapsed(started), result.getUsage());
                return result;
            } catch (RuntimeException ex) {
                markRouteFailure(route.get("routeId"), ex);
                lastFailure = ex;
            }
        }
        recordSafely(principal.id(), group, null, "FAILED", elapsed(started), Map.of());
        throw lastFailure == null ? new BusinessException(503, "Model provider unavailable") : lastFailure;
    }

    private void markRouteSuccess(Long routeId) {
        jdbc.update("UPDATE model_gateway_route SET failure_count=0,unhealthy_until=NULL,last_checked_at=CURRENT_TIMESTAMP,last_error_code=NULL WHERE id=?", routeId);
    }

    private void markRouteFailure(Long routeId, RuntimeException failure) {
        String code = failure instanceof BusinessException ? "UPSTREAM_REJECTED" : "UPSTREAM_UNAVAILABLE";
        jdbc.update("UPDATE model_gateway_route SET failure_count=failure_count+1,last_checked_at=CURRENT_TIMESTAMP,last_error_code=?,unhealthy_until=CASE WHEN failure_count+1 >= 3 THEN DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 60 SECOND) ELSE unhealthy_until END WHERE id=?", code, routeId);
    }
    public List<Map<String,Object>> models(GatewayPrincipal principal) {
        if (!"PERSONAL".equals(principal.scope())) throw new BusinessException(403, "Key scope not supported");
        return jdbc.query("SELECT slug,name FROM model_gateway_group WHERE enabled=TRUE AND scope='PERSONAL' AND owner_user_id=? ORDER BY slug", (rs, n) -> Map.of("id", rs.getString("slug"), "object", "model", "owned_by", "smartops"), principal.ownerUserId());
    }

    private void enforceQuota(Long keyId, Long ownerUserId, String group) {
        List<Map<String, Long>> limits = jdbc.query("SELECT request_limit_24h,token_limit_24h FROM model_gateway_key WHERE id=?", (rs, n) -> Map.of("requests", rs.getObject("request_limit_24h") == null ? -1L : rs.getLong("request_limit_24h"), "tokens", rs.getObject("token_limit_24h") == null ? -1L : rs.getLong("token_limit_24h")), keyId);
        if (limits.isEmpty()) throw new BusinessException(401, "Invalid gateway key");
        long requestLimit = limits.get(0).get("requests"), tokenLimit = limits.get(0).get("tokens");
        if (requestLimit < 0 && tokenLimit < 0) return;
        Map<String, Long> usage = jdbc.query("SELECT COUNT(*) calls, COALESCE(SUM(total_tokens),0) tokens FROM model_gateway_invocation WHERE key_id=? AND created_at >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 24 HOUR)", (rs, n) -> Map.of("calls", rs.getLong("calls"), "tokens", rs.getLong("tokens")), keyId).stream().findFirst().orElse(Map.of("calls", 0L, "tokens", 0L));
        if (requestLimit >= 0 && usage.get("calls") >= requestLimit) throw new BusinessException(429, "Gateway request quota exceeded");
        if (tokenLimit >= 0 && usage.get("tokens") >= tokenLimit) throw new BusinessException(429, "Gateway token quota exceeded");
        List<Map<String, Long>> groupLimits = jdbc.query("SELECT request_limit_24h,token_limit_24h FROM model_gateway_group WHERE slug=? AND owner_user_id=?", (rs, n) -> Map.of("requests", rs.getObject("request_limit_24h") == null ? -1L : rs.getLong("request_limit_24h"), "tokens", rs.getObject("token_limit_24h") == null ? -1L : rs.getLong("token_limit_24h")), group, ownerUserId);
        if (!groupLimits.isEmpty()) {
            long groupRequestLimit = groupLimits.get(0).get("requests"), groupTokenLimit = groupLimits.get(0).get("tokens");
            if (groupRequestLimit >= 0 || groupTokenLimit >= 0) {
                Map<String, Long> groupUsage = jdbc.query("SELECT COUNT(*) calls, COALESCE(SUM(i.total_tokens),0) tokens FROM model_gateway_invocation i JOIN model_gateway_key k ON k.id=i.key_id WHERE k.owner_user_id=? AND i.group_slug=? AND i.created_at >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 24 HOUR)", (rs, n) -> Map.of("calls", rs.getLong("calls"), "tokens", rs.getLong("tokens")), ownerUserId, group).stream().findFirst().orElse(Map.of("calls", 0L, "tokens", 0L));
                if (groupRequestLimit >= 0 && groupUsage.get("calls") >= groupRequestLimit) throw new BusinessException(429, "Model group request quota exceeded");
                if (groupTokenLimit >= 0 && groupUsage.get("tokens") >= groupTokenLimit) throw new BusinessException(429, "Model group token quota exceeded");
            }
        }
    }

    public List<Map<String, Object>> keys(Long ownerUserId) {
        if (ownerUserId == null) throw new BusinessException(401, "User required");
        return jdbc.query("SELECT id,name,key_prefix,scope,expires_at,revoked_at,request_limit_24h,token_limit_24h,created_at FROM model_gateway_key WHERE owner_user_id=? ORDER BY created_at DESC", (rs, n) -> Map.of(
                "id", rs.getLong("id"), "name", rs.getString("name"), "prefix", rs.getString("key_prefix"),
                "scope", rs.getString("scope"), "expiresAt", rs.getTimestamp("expires_at") == null ? "" : rs.getTimestamp("expires_at").toInstant().toString(),
                "revoked", rs.getTimestamp("revoked_at") != null, "requestLimit24h", rs.getObject("request_limit_24h") == null ? -1L : rs.getLong("request_limit_24h"), "tokenLimit24h", rs.getObject("token_limit_24h") == null ? -1L : rs.getLong("token_limit_24h"), "createdAt", rs.getTimestamp("created_at").toInstant().toString()), ownerUserId);
    }

    @Transactional
    public void setQuota(Long ownerUserId, Long id, Long requestLimit, Long tokenLimit) {
        if (ownerUserId == null || id == null || (requestLimit != null && requestLimit < 0) || (tokenLimit != null && tokenLimit < 0)) throw new BusinessException(400, "Invalid gateway quota");
        int updated = jdbc.update("UPDATE model_gateway_key SET request_limit_24h=?,token_limit_24h=? WHERE id=? AND owner_user_id=?", requestLimit, tokenLimit, id, ownerUserId);
        if (updated == 0) throw new BusinessException(404, "Gateway key unavailable");
    }

    @Transactional
    public void setGroupQuota(Long ownerUserId, String slug, Long requestLimit, Long tokenLimit) {
        if (ownerUserId == null || slug == null || (requestLimit != null && requestLimit < 0) || (tokenLimit != null && tokenLimit < 0)) throw new BusinessException(400, "Invalid model group quota");
        int updated = jdbc.update("UPDATE model_gateway_group SET request_limit_24h=?,token_limit_24h=? WHERE slug=? AND owner_user_id=?", requestLimit, tokenLimit, slug, ownerUserId);
        if (updated == 0) throw new BusinessException(404, "Model group unavailable");
    }

    public List<Map<String, Object>> routes(Long ownerUserId, String slug) {
        if (ownerUserId == null || slug == null) throw new BusinessException(400, "Invalid model group");
        return jdbc.query("SELECT r.id,r.connection_id,r.priority,r.weight,r.enabled,r.failure_count,r.unhealthy_until,r.last_checked_at,r.last_error_code FROM model_gateway_group g JOIN model_gateway_route r ON r.group_id=g.id WHERE g.slug=? AND g.owner_user_id=? AND g.scope='PERSONAL' ORDER BY r.priority,r.weight DESC", (rs, n) -> Map.of(
                "id", rs.getLong("id"), "connectionId", rs.getLong("connection_id"), "priority", rs.getInt("priority"), "weight", rs.getInt("weight"), "enabled", rs.getBoolean("enabled"), "failureCount", rs.getInt("failure_count"), "healthy", rs.getTimestamp("unhealthy_until") == null || rs.getTimestamp("unhealthy_until").toInstant().isBefore(Instant.now()), "lastError", rs.getString("last_error_code") == null ? "" : rs.getString("last_error_code")), slug, ownerUserId);
    }

    public List<Map<String, Object>> groups(Long ownerUserId) {
        if (ownerUserId == null) throw new BusinessException(401, "User required");
        return jdbc.query("SELECT id,slug,name,enabled,request_limit_24h,token_limit_24h FROM model_gateway_group WHERE owner_user_id=? AND scope='PERSONAL' ORDER BY slug", (rs, n) -> Map.of(
                "id", rs.getLong("id"), "slug", rs.getString("slug"), "name", rs.getString("name"), "enabled", rs.getBoolean("enabled"),
                "requestLimit24h", rs.getObject("request_limit_24h") == null ? -1L : rs.getLong("request_limit_24h"),
                "tokenLimit24h", rs.getObject("token_limit_24h") == null ? -1L : rs.getLong("token_limit_24h")), ownerUserId);
    }

    @Transactional
    public void configurePersonalGroup(Long ownerUserId, String slug, String name, Long connectionId) {
        validateGroup(ownerUserId, slug, name, connectionId);
        connections.getRuntimeConfiguration(ownerUserId, connectionId);
        var owner = jdbc.query("SELECT owner_user_id FROM model_gateway_group WHERE slug=?", (rs, n) -> rs.getLong(1), slug).stream().findFirst().orElse(null);
        if (owner != null && !ownerUserId.equals(owner)) throw new BusinessException(409, "Model group name already exists");
        Long groupId = jdbc.query("SELECT id FROM model_gateway_group WHERE slug=? AND owner_user_id=? AND scope='PERSONAL'", (rs, n) -> rs.getLong(1), slug, ownerUserId).stream().findFirst().orElse(null);
        if (groupId == null) {
            groupId = nextId();
            jdbc.update("INSERT INTO model_gateway_group(id,owner_user_id,name,slug,scope) VALUES(?,?,?,?,?)", groupId, ownerUserId, name.trim(), slug, "PERSONAL");
            jdbc.update("INSERT INTO model_gateway_route(id,group_id,connection_id,priority,weight) VALUES(?,?,?,?,?)", nextId(), groupId, connectionId, 1, 100);
        } else {
            jdbc.update("UPDATE model_gateway_group SET name=?,enabled=TRUE WHERE id=?", name.trim(), groupId);
        }
    }

    @Transactional
    public void renameGroup(Long ownerUserId, String slug, String name) {
        if (ownerUserId == null || slug == null || name == null || name.isBlank() || name.length() > 120) throw new BusinessException(400, "Invalid model group");
        int updated = jdbc.update("UPDATE model_gateway_group SET name=? WHERE slug=? AND owner_user_id=? AND scope='PERSONAL'", name.trim(), slug, ownerUserId);
        if (updated == 0) throw new BusinessException(404, "Model group unavailable");
    }

    @Transactional
    public void deleteGroup(Long ownerUserId, String slug) {
        if (ownerUserId == null || slug == null) throw new BusinessException(400, "Invalid model group");
        Long groupId = jdbc.query("SELECT id FROM model_gateway_group WHERE slug=? AND owner_user_id=? AND scope='PERSONAL'", (rs, n) -> rs.getLong(1), slug, ownerUserId).stream().findFirst().orElse(null);
        if (groupId == null) throw new BusinessException(404, "Model group unavailable");
        jdbc.update("DELETE FROM model_gateway_route WHERE group_id=?", groupId);
        int updated = jdbc.update("DELETE FROM model_gateway_group WHERE id=?", groupId);
        if (updated == 0) throw new BusinessException(404, "Model group unavailable");
    }

    @Transactional
    public void updateRoute(Long ownerUserId, String slug, Long routeId, int priority, int weight) {
        if (ownerUserId == null || slug == null || routeId == null || priority < 0 || priority > 10000 || weight < 1 || weight > 1000) throw new BusinessException(400, "Invalid model route");
        int updated = jdbc.update("UPDATE model_gateway_route SET priority=?,weight=? WHERE id=? AND group_id IN (SELECT id FROM model_gateway_group WHERE slug=? AND owner_user_id=? AND scope='PERSONAL')", priority, weight, routeId, slug, ownerUserId);
        if (updated == 0) throw new BusinessException(404, "Model route unavailable");
    }

    @Transactional
    public void setRouteEnabled(Long ownerUserId, String slug, Long routeId, boolean enabled) {
        if (ownerUserId == null || slug == null || routeId == null) throw new BusinessException(400, "Invalid model route");
        int updated = jdbc.update("UPDATE model_gateway_route SET enabled=? WHERE id=? AND group_id IN (SELECT id FROM model_gateway_group WHERE slug=? AND owner_user_id=? AND scope='PERSONAL')", enabled, routeId, slug, ownerUserId);
        if (updated == 0) throw new BusinessException(404, "Model route unavailable");
    }

    @Transactional
    public void deleteRoute(Long ownerUserId, String slug, Long routeId) {
        if (ownerUserId == null || slug == null || routeId == null) throw new BusinessException(400, "Invalid model route");
        int updated = jdbc.update("DELETE FROM model_gateway_route WHERE id=? AND group_id IN (SELECT id FROM model_gateway_group WHERE slug=? AND owner_user_id=? AND scope='PERSONAL')", routeId, slug, ownerUserId);
        if (updated == 0) throw new BusinessException(404, "Model route unavailable");
    }

    private void validateGroup(Long ownerUserId, String slug, String name, Long connectionId) {
        if (ownerUserId == null || connectionId == null || slug == null || !slug.matches("[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}") || name == null || name.isBlank() || name.length() > 120) throw new BusinessException(400, "Invalid model group");
    }

    public Map<String, Object> analytics(Long ownerUserId) {
        if (ownerUserId == null) throw new BusinessException(401, "User required");
        Map<String, Object> summary = jdbc.query("SELECT COUNT(*) calls, COALESCE(SUM(status='SUCCESS'),0) successes, COALESCE(AVG(duration_ms),0) latency, COALESCE(SUM(total_tokens),0) tokens FROM model_gateway_invocation i JOIN model_gateway_key k ON k.id=i.key_id WHERE k.owner_user_id=? AND i.created_at >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 24 HOUR)", (rs, n) -> Map.<String,Object>of("calls", rs.getLong("calls"), "successes", rs.getLong("successes"), "latencyMs", Math.round(rs.getDouble("latency")), "tokens", rs.getLong("tokens")), ownerUserId).stream().findFirst().orElse(Map.of("calls", 0L, "successes", 0L, "latencyMs", 0L, "tokens", 0L));
        List<Map<String, Object>> recent = jdbc.query("SELECT i.group_slug,i.status,i.duration_ms,i.total_tokens,i.created_at FROM model_gateway_invocation i JOIN model_gateway_key k ON k.id=i.key_id WHERE k.owner_user_id=? ORDER BY i.created_at DESC LIMIT 20", (rs, n) -> Map.of("group", rs.getString("group_slug"), "status", rs.getString("status"), "durationMs", rs.getLong("duration_ms"), "tokens", rs.getObject("total_tokens") == null ? 0L : rs.getLong("total_tokens"), "createdAt", rs.getTimestamp("created_at").toInstant().toString()), ownerUserId);
        return Map.of("summary", summary, "recent", recent);
    }

    public void revoke(Long ownerUserId, Long id) { jdbc.update("UPDATE model_gateway_key SET revoked_at=CURRENT_TIMESTAMP WHERE id=? AND owner_user_id=?", id, ownerUserId); }
    @Transactional
    public void configureGroup(Long ownerUserId, String slug, String name, Long connectionId) {
        if (ownerUserId == null || connectionId == null || slug == null || !slug.matches("[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}") || name == null || name.isBlank() || name.length() > 120) throw new BusinessException(400, "Invalid model group");
        connections.getRuntimeConfiguration(ownerUserId, connectionId);
        var existing = jdbc.query("SELECT id,owner_user_id FROM model_gateway_group WHERE slug=?", (rs, n) -> Map.<String,Object>of("id", rs.getLong("id"), "owner", rs.getLong("owner_user_id")), slug);
        if (!existing.isEmpty() && !ownerUserId.equals(existing.get(0).get("owner"))) throw new BusinessException(409, "Model group name already exists");
        Long actual;
        if (existing.isEmpty()) { actual = nextId(); jdbc.update("INSERT INTO model_gateway_group(id,owner_user_id,name,slug,scope) VALUES(?,?,?,?,?)", actual, ownerUserId, name.trim(), slug, "PERSONAL"); }
        else { actual = ((Number) existing.get(0).get("id")).longValue(); jdbc.update("UPDATE model_gateway_group SET name=?,enabled=TRUE WHERE id=? AND owner_user_id=?", name.trim(), actual, ownerUserId); jdbc.update("DELETE FROM model_gateway_route WHERE group_id=?", actual); }
        jdbc.update("INSERT INTO model_gateway_route(id,group_id,connection_id,priority,weight) VALUES(?,?,?,?,?)", nextId(), actual, connectionId, 1, 100);
    }

    @Transactional
    public void addRoute(Long ownerUserId, String slug, Long connectionId, int priority, int weight) {
        if (ownerUserId == null || connectionId == null || slug == null || !slug.matches("[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}") || priority < 0 || priority > 10000 || weight < 1 || weight > 1000) throw new BusinessException(400, "Invalid model route");
        connections.getRuntimeConfiguration(ownerUserId, connectionId);
        Long groupId = jdbc.query("SELECT id FROM model_gateway_group WHERE slug=? AND owner_user_id=? AND scope='PERSONAL'", (rs, n) -> rs.getLong(1), slug, ownerUserId).stream().findFirst().orElseThrow(() -> new BusinessException(404, "Model group unavailable"));
        jdbc.update("INSERT INTO model_gateway_route(id,group_id,connection_id,priority,weight) VALUES(?,?,?,?,?)", nextId(), groupId, connectionId, priority, weight);
    }

    @Transactional
    public void setRouteEnabled(Long ownerUserId, Long routeId, boolean enabled) {
        if (ownerUserId == null || routeId == null) throw new BusinessException(400, "Invalid model route");
        int updated = jdbc.update("UPDATE model_gateway_route SET enabled=? WHERE id=? AND group_id IN (SELECT id FROM model_gateway_group WHERE owner_user_id=? AND scope='PERSONAL')", enabled, routeId, ownerUserId);
        if (updated == 0) throw new BusinessException(404, "Model route unavailable");
    }

    @Transactional
    public void deleteRoute(Long ownerUserId, Long routeId) {
        if (ownerUserId == null || routeId == null) throw new BusinessException(400, "Invalid model route");
        int updated = jdbc.update("DELETE FROM model_gateway_route WHERE id=? AND group_id IN (SELECT id FROM model_gateway_group WHERE owner_user_id=? AND scope='PERSONAL')", routeId, ownerUserId);
        if (updated == 0) throw new BusinessException(404, "Model route unavailable");
    }
    private void recordSafely(Long keyId, String group, String model, String status, long duration, Map<String,Object> usage) { try { jdbc.update("INSERT INTO model_gateway_invocation(id,key_id,group_slug,model_name,status,duration_ms,input_tokens,output_tokens,total_tokens) VALUES(?,?,?,?,?,?,?,?,?)", nextId(), keyId, group, model, status, duration, number(usage,"prompt_tokens"), number(usage,"completion_tokens"), number(usage,"total_tokens")); } catch (RuntimeException ex) { org.slf4j.LoggerFactory.getLogger(ModelGatewayService.class).warn("Gateway audit write failed for group {}", group); } }
    private Long number(Map<String,Object> map, String key) { Object value = map.get(key); return value instanceof Number n ? n.longValue() : null; }
    private long elapsed(long start) { return (System.nanoTime() - start) / 1_000_000; }
    private String randomPart(int length) { byte[] bytes = new byte[length]; random.nextBytes(bytes); return HexFormat.of().formatHex(bytes); }
    private long nextId() { return random.nextLong() & Long.MAX_VALUE; }
    static String hash(String value) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); } catch (Exception ex) { throw new IllegalStateException(ex); } }
}
