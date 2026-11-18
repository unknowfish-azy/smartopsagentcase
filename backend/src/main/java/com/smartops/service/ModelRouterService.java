package com.smartops.service;

import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.service.modelconfig.ModelConfigRegistry;
import com.smartops.service.modelconfig.ModelConfigSnapshot;
import com.smartops.service.modelconfig.ModelRoutingProperties;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 模型路由器：按请求意图 + connection 能力标签自动选模型连接。
 *
 * <p>二段决策（借鉴 ExperienceRecall 教训：禁止"用单一 LLM 路由同时承担媒体生成选择"）：</p>
 * <ol>
 *   <li><b>意图→能力</b>：从 prompt/systemPrompt 抽取能力信号（vision/tool-calling/reasoning/fast）；</li>
 *   <li><b>能力→连接</b>：在同 group 内对所有 enabled connection 做能力匹配评分，取 top-N。</li>
 * </ol>
 *
 * <p>降级保护（借鉴"路由策略与实际能力脱节会导致全链路崩"教训）：</p>
 * <ul>
 *   <li>AUTO 模式无候选 → 回退 MANUAL（沿用 route 表）；</li>
 *   <li>MANUAL 也无候选 → 取 group 内第一个 enabled connection；</li>
 *   <li>仍无 → 返回空列表，由调用方抛 404。</li>
 * </ul>
 */
@Slf4j
@Service
public class ModelRouterService {

    private final JdbcTemplate jdbc;
    private final ModelConfigRegistry configRegistry;
    private final ModelRoutingProperties routingProperties;

    public ModelRouterService(JdbcTemplate jdbc, ModelConfigRegistry configRegistry,
                              ModelRoutingProperties routingProperties) {
        this.jdbc = jdbc;
        this.configRegistry = configRegistry;
        this.routingProperties = routingProperties;
    }

    /** 路由结果：一组候选连接（按优先级排序）。 */
    public record RoutedConnection(Long connectionId, Long routeId, String reason, double score) {}

    /**
     * 为某个 group 选出候选连接列表。按优先级从高到低，与旧 route 表的 priority 语义一致。
     *
     * @param group         slug（如 "ops", "agent-diag"）
     * @param ownerUserId   资源归属用户（group 和 connection 都属此人）
     * @param request       原始请求（从中提取意图信号）
     * @return 非空列表（最差也会回退到默认 connection）
     */
    public List<RoutedConnection> selectConnections(String group, Long ownerUserId,
                                                     ModelInvocationRequest request) {
        if (group == null || ownerUserId == null) return List.of();

        // 已发布配置版本：走内存快照，不查配置表；灰度期按"用户+模型组"稳定分桶
        ModelConfigSnapshot snapshot = configRegistry.resolve(ownerUserId, group);
        if (snapshot != null) {
            var routed = selectFromSnapshot(snapshot, group, ownerUserId, request);
            if (!routed.isEmpty()) return routed;
            log.debug("router snapshot has no candidate for group {}, falling back to working copy", group);
        }

        // 1) 查 group 配置
        var groupMeta = jdbc.query(
                "SELECT route_mode,default_capability FROM model_gateway_group "
                        + "WHERE slug=? AND owner_user_id=? AND enabled=TRUE",
                (rs, n) -> Map.of("mode", rs.getString("route_mode"),
                        "defaultCapability", rs.getString("default_capability")),
                group, ownerUserId);
        boolean auto = groupMeta.stream().findFirst()
                .map(m -> "AUTO".equalsIgnoreCase((String) m.get("mode"))).orElse(false);
        String defaultCap = groupMeta.stream().findFirst()
                .map(m -> (String) m.get("defaultCapability")).orElse(null);

        // 2) AUTO 路由（优先）
        if (auto) {
            var routed = autoSelect(group, ownerUserId, request, defaultCap);
            if (!routed.isEmpty()) return routed;
            log.debug("router AUTO returned no candidates for group {}, falling back to MANUAL", group);
        }

        // 3) MANUAL 路由（沿用原有 route 表，向后兼容）
        var routes = jdbc.query(
                "SELECT r.id,r.connection_id FROM model_gateway_group g "
                        + "JOIN model_gateway_route r ON r.group_id=g.id "
                        + "WHERE g.slug=? AND g.scope='PERSONAL' AND g.owner_user_id=? "
                        + "AND g.enabled=TRUE AND r.enabled=TRUE "
                        + "AND (r.unhealthy_until IS NULL OR r.unhealthy_until <= CURRENT_TIMESTAMP) "
                        + "ORDER BY r.priority ASC, r.weight DESC",
                (rs, n) -> new RoutedConnection(rs.getLong("connection_id"), rs.getLong("id"),
                        "MANUAL route", 1.0),
                group, ownerUserId);
        if (!routes.isEmpty()) return routes;

        // 4) 最终兜底：取用户下第一个 enabled connection
        var fallback = jdbc.query(
                "SELECT id FROM model_connections WHERE user_id=? AND enabled=1 ORDER BY id ASC LIMIT 1",
                (rs, n) -> new RoutedConnection(rs.getLong("id"), null, "FALLBACK default", 0.5),
                ownerUserId);
        if (!fallback.isEmpty()) {
            log.debug("router using fallback connection for group {}", group);
            return fallback;
        }

        return List.of();
    }

    /* ── 快照路由：已发布版本优先，语义与工作区直读一致 ───────── */

    private List<RoutedConnection> selectFromSnapshot(ModelConfigSnapshot snapshot, String slug,
                                                      Long ownerUserId, ModelInvocationRequest request) {
        if (snapshot.groups() == null) return List.of();
        var group = snapshot.groups().stream()
                .filter(g -> g.enabled() && slug.equals(g.slug())
                        && ownerUserId.equals(g.ownerUserId()) && "PERSONAL".equals(g.scope()))
                .findFirst().orElse(null);
        if (group == null) return List.of();

        List<ModelConfigSnapshot.Connection> connections = snapshot.connections() == null
                ? List.of()
                : snapshot.connections().stream()
                        .filter(c -> c.enabled() && ownerUserId.equals(c.userId()))
                        .toList();

        if ("AUTO".equalsIgnoreCase(group.routeMode())) {
            var routed = autoSelectFromSnapshot(connections, request, group.defaultCapability());
            if (!routed.isEmpty()) return routed;
            log.debug("router snapshot AUTO returned no candidates for group {}, falling back to MANUAL", slug);
        }

        List<ModelConfigSnapshot.Route> routes = group.routes() == null ? List.of() : group.routes();
        Set<Long> healthy = healthyRouteIds(routes);
        var ordered = routes.stream()
                .filter(ModelConfigSnapshot.Route::enabled)
                .filter(route -> healthy.contains(route.id()))
                .filter(route -> connections.stream().anyMatch(c -> c.id().equals(route.connectionId())))
                .sorted(Comparator.comparingInt(ModelConfigSnapshot.Route::priority)
                        .thenComparing(Comparator.comparingInt(ModelConfigSnapshot.Route::weight).reversed()))
                .map(route -> new RoutedConnection(route.connectionId(), route.id(), "MANUAL route", 1.0))
                .toList();
        if (!ordered.isEmpty()) return ordered;

        if (!connections.isEmpty()) {
            return List.of(new RoutedConnection(connections.get(0).id(), null, "FALLBACK default", 0.5));
        }
        return List.of();
    }

    /** 只读一次库拿路由健康状态；配置本身仍全部来自快照。 */
    private Set<Long> healthyRouteIds(List<ModelConfigSnapshot.Route> routes) {
        if (routes.isEmpty()) return Set.of();
        String ids = routes.stream().map(route -> String.valueOf(route.id())).collect(Collectors.joining(","));
        return new HashSet<>(jdbc.query(
                "SELECT id FROM model_gateway_route WHERE id IN (" + ids + ") "
                        + "AND (unhealthy_until IS NULL OR unhealthy_until <= CURRENT_TIMESTAMP)",
                (rs, n) -> rs.getLong("id")));
    }

    private List<RoutedConnection> autoSelectFromSnapshot(List<ModelConfigSnapshot.Connection> connections,
                                                          ModelInvocationRequest request, String defaultCap) {
        Set<String> signals = extractCapabilitySignals(request);
        if (defaultCap != null && !defaultCap.isBlank()) signals.add(defaultCap);

        List<RoutedConnection> scored = new ArrayList<>();
        for (ModelConfigSnapshot.Connection connection : connections) {
            List<String> caps = connection.capabilities() == null ? List.of() : connection.capabilities();
            double score = score(signals, caps, request);
            String reason = signals.isEmpty()
                    ? "default chat"
                    : "matched " + caps.stream().filter(signals::contains)
                            .reduce((a, b) -> a + "," + b).orElse("none");
            scored.add(new RoutedConnection(connection.id(), null, reason, score));
        }
        scored.sort((a, b) -> Double.compare(b.score(), a.score()));
        return scored;
    }

    /* ── AUTO 路由：意图→能力→连接 ─────────────────────────── */

    private List<RoutedConnection> autoSelect(String group, Long ownerUserId,
                                              ModelInvocationRequest request, String defaultCap) {
        Set<String> signals = extractCapabilitySignals(request);
        // default_capability 是 group 管理员预设的保底能力
        if (defaultCap != null && !defaultCap.isBlank()) signals.add(defaultCap);

        // 取该用户下所有 enabled connection（不依赖 route 表）
        var conns = jdbc.query(
                "SELECT id, name, model_name, capabilities FROM model_connections "
                        + "WHERE user_id=? AND enabled=1 ORDER BY id ASC",
                (rs, n) -> {
                    long id = rs.getLong("id");
                    String capsJson = rs.getString("capabilities");
                    List<String> caps = parseCaps(capsJson);
                    return new Object[] {id, rs.getString("model_name"), caps};
                },
                ownerUserId);

        List<RoutedConnection> scored = new ArrayList<>();
        for (Object[] row : conns) {
            long id = (Long) row[0];
            String modelName = (String) row[1];
            @SuppressWarnings("unchecked")
            List<String> caps = (List<String>) row[2];
            double score = score(signals, caps, request);
            String reason = signals.isEmpty()
                    ? "default chat"
                    : "matched " + caps.stream().filter(signals::contains).reduce((a, b) -> a + "," + b).orElse("none");
            scored.add(new RoutedConnection(id, null, reason, score));
        }
        scored.sort((a, b) -> Double.compare(b.score(), a.score()));

        // 基础 chat 能力必须有；否则这条 connection 不能对话（比如纯 embedding 连接）
        List<RoutedConnection> filtered = new ArrayList<>();
        for (RoutedConnection rc : scored) {
            // 只要 connection 有任何能力标签就算可对话（没标签时默认 chat=ok）
            filtered.add(rc);
        }
        return filtered;
    }

    /**
     * 意图→能力信号抽取。借鉴 ExperienceRecall 教训：用"最长优先 + 输入清洗"避免
     * 短 pattern 抢先命中导致的误判（如 qwen3 误覆盖 qwen3.7-plus）。
     */
    private List<ModelRoutingProperties.IntentPattern> orderedPatterns() {
        List<ModelRoutingProperties.IntentPattern> source = routingProperties.getIntentPatterns();
        if (source == null || source.isEmpty()) {
            source = ModelRoutingProperties.defaultPatterns();
        }
        return source.stream()
                .filter(pattern -> pattern.getKeyword() != null && !pattern.getKeyword().isBlank()
                        && pattern.getCapability() != null)
                .sorted(Comparator.comparingInt(
                        (ModelRoutingProperties.IntentPattern pattern) -> pattern.getKeyword().length()).reversed())
                .toList();
    }

    private Set<String> extractCapabilitySignals(ModelInvocationRequest request) {
        Set<String> out = new HashSet<>();
        String text = (request.getSystemPrompt() == null ? "" : request.getSystemPrompt()) + " "
                + (request.getPrompt() == null ? "" : request.getPrompt());
        text = text.toLowerCase();

        // 关键词 → 能力信号：词表来自配置（运营可改），长 pattern 优先匹配
        for (ModelRoutingProperties.IntentPattern pattern : orderedPatterns()) {
            if (text.contains(pattern.getKeyword())) {
                out.add(pattern.getCapability());
                break;  // 一种信号命中一次即可，避免同词多义
            }
        }

        // temperature > 0.7 暗示需要推理型模型
        if (request.getTemperature() != null && request.getTemperature() > 0.7) {
            out.add("reasoning");
        }

        // 所有对话都需要基础 chat 能力
        out.add("chat");
        return out;
    }

    /** 能力匹配评分：信号数加权 + 额外信号扣分（过度高配）。 */
    private double score(Set<String> signals, List<String> caps, ModelInvocationRequest request) {
        if (caps.isEmpty()) caps = List.of("chat");  // 没声明能力默认 chat
        double base = 0.0;
        for (String sig : signals) {
            if (caps.contains(sig)) base += 1.0;
            else if ("chat".equals(sig)) base += 0.5;  // 缺 chat 但有别的能力也算部分匹配
        }
        // connection 有信号外的能力也不扣分（"能做 vision 但只需要 chat" 是好事）
        return base;
    }

    private static List<String> parseCaps(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            // MySQL JSON_ARRAY 读出来是 "[\"chat\",\"vision\"]"
            return com.fasterxml.jackson.databind.JsonNode.class == null
                    ? naiveParseArray(json) : parseArray(json);
        } catch (Exception ignored) {
            return naiveParseArray(json);
        }
    }

    private static List<String> parseArray(String json) {
        try {
            var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            var node = mapper.readTree(json);
            if (!node.isArray()) return List.of();
            List<String> out = new ArrayList<>();
            node.forEach(n -> out.add(n.asText()));
            return out;
        } catch (Exception e) {
            return naiveParseArray(json);
        }
    }

    private static List<String> naiveParseArray(String json) {
        // 兜底：手搓 JSON 数组解析，不依赖 Jackson
        List<String> out = new ArrayList<>();
        if (json == null) return out;
        json = json.trim();
        if (!json.startsWith("[") || !json.endsWith("]")) return out;
        for (String part : json.substring(1, json.length() - 1).split(",")) {
            String s = part.trim();
            if (s.startsWith("\"") && s.endsWith("\"")) s = s.substring(1, s.length() - 1);
            if (!s.isBlank()) out.add(s);
        }
        return out;
    }
}
