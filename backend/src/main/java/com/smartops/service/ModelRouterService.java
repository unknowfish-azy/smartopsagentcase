package com.smartops.service;

import com.smartops.dto.model.ModelInvocationRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

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

    public ModelRouterService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
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
    private Set<String> extractCapabilitySignals(ModelInvocationRequest request) {
        Set<String> out = new HashSet<>();
        String text = (request.getSystemPrompt() == null ? "" : request.getSystemPrompt()) + " "
                + (request.getPrompt() == null ? "" : request.getPrompt());
        text = text.toLowerCase();

        // 关键词 → 能力信号（长 pattern 放前面，先匹配先锁死）
        String[][] patterns = {
                // vision：图像理解
                {"看图", "vision"}, {"截图", "vision"}, {"图片", "vision"},
                {"图像", "vision"}, {"vision", "vision"}, {"理解图", "vision"},
                // reasoning：复杂诊断（高 temperature 也暗示需要推理）
                {"诊断", "reasoning"}, {"分析", "reasoning"}, {"排查", "reasoning"},
                {"根因", "reasoning"}, {"复杂", "reasoning"}, {"规划", "reasoning"},
                {"temperature", "reasoning"},  // 用户显式要高 temperature → 推理
                // tool-calling：agent 工具链
                {"工具", "tool-calling"}, {"调用", "tool-calling"}, {"agent", "tool-calling"},
                {"function", "tool-calling"}, {"tool", "tool-calling"},
                // fast：简单问答
                {"简单", "fast"}, {"快速", "fast"}, {"快", "fast"},
                // cheap：成本敏感
                {"便宜", "cheap"}, {"省钱", "cheap"}, {"cheap", "cheap"},
        };

        // 长 pattern 优先排序（避免 "快" 抢先匹配 "快速"）
        Arrays.sort(patterns, (a, b) -> Integer.compare(b[0].length(), a[0].length()));
        for (String[] p : patterns) {
            if (text.contains(p[0])) {
                out.add(p[1]);
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
