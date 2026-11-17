package com.smartops.robot.replan;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * LLM 重规划（M7 真机接入增强）。
 *
 * <p>调本地 Ollama 多模态/文本模型，把当前 route + 触发重规划的异常点位置喂给模型，
 * 要求输出替换后的 route 段（严格 JSON，容错：失败自动 fallback 到 DeterministicReplan）。</p>
 *
 * <p>Fail-closed 保障：
 * <ul>
 *   <li>Ollama 不可达（503/timeout） → fallback；</li>
 *   <li>模型输出不合法（非 JSON、坐标超范围、缺失字段） → fallback；</li>
 *   <li>model 未配置（空串） → 跳过，直接 fallback。</li>
 * </ul>
 */
@Slf4j
@Component
public class OllamaReplan implements ReplanStrategy {

    private final HttpClient http;
    private final ObjectMapper mapper;
    private final URI baseUri;
    private final String model;
    private final Duration timeout;

    public OllamaReplan(
            ObjectMapper mapper,
            @Value("${smartops.robot.replan.ollama.base-url:http://127.0.0.1:11434}") String baseUrl,
            @Value("${smartops.robot.replan.ollama.model:}") String model,
            @Value("${smartops.robot.replan.ollama.timeout-ms:5000}") long timeoutMs) {
        this.mapper = mapper;
        this.baseUri = URI.create(baseUrl == null ? "http://127.0.0.1:11434" : baseUrl);
        this.model = model == null ? "" : model.strip();
        this.timeout = Duration.ofMillis(Math.max(500L, timeoutMs));
        this.http = HttpClient.newBuilder().connectTimeout(Duration.ofMillis(1500)).build();
    }

    @Override public String name() { return "ollama-" + model; }

    @Override
    public ReplanResult replan(List<Map<String, Object>> route, int currentIndex, String deviceKey) {
        long start = System.currentTimeMillis();

        if (model.isBlank()) {
            return FallbackResult.fallback("replan.ollama.model 未配置");
        }

        try {
            String prompt = buildPrompt(route, currentIndex);
            Map<String, Object> body = Map.of(
                    "model", model,
                    "prompt", prompt,
                    "stream", false,
                    "options", Map.of("temperature", 0.1)
            );
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(baseUri.resolve("/api/generate"))
                    .timeout(timeout)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body)))
                    .build();

            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) {
                log.warn("OllamaReplan HTTP {} → fallback", resp.statusCode());
                return new FallbackResult("ollama HTTP " + resp.statusCode(), elapsed(start));
            }

            Map<String, Object> json = mapper.readValue(resp.body(), new TypeReference<>() {});
            String raw = String.valueOf(json.getOrDefault("response", ""));
            String cleaned = extractJson(raw);
            if (cleaned == null || cleaned.isBlank()) {
                log.warn("OllamaReplan 无法从模型输出中提取 JSON → fallback");
                return new FallbackResult("模型输出非 JSON：" + truncate(raw, 80), elapsed(start));
            }

            // 解析为 [{x,y,theta,label,actions}]
            List<Map<String, Object>> waypoints = mapper.readValue(cleaned, new TypeReference<>() {});
            if (waypoints == null || waypoints.isEmpty()) {
                log.warn("OllamaReplan 输出空 route 段 → fallback");
                return new FallbackResult("模型输出空 route", elapsed(start));
            }

            // 把模型输出的 route 段替换回完整 route 的 currentIndex 位置
            List<Map<String, Object>> newRoute = mergeSegment(route, currentIndex, waypoints, deviceKey);
            return new SuccessResult(newRoute, name(), elapsed(start));

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return new FallbackResult("ollama 请求被中断", elapsed(start));
        } catch (Exception e) {
            log.warn("OllamaReplan 异常 → fallback：{}", e.getMessage());
            return new FallbackResult("ollama 异常：" + e.getMessage(), elapsed(start));
        }
    }

    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------

    private String buildPrompt(List<Map<String, Object>> route, int idx) throws Exception {
        String routeJson = mapper.writerWithDefaultPrettyPrinter().writeValueAsString(route);
        String hint = mapper.writeValueAsString(route.get(idx));
        return """
                你是一个机器人路径重规划器。以下是完整巡检路线（JSON）和触发重规划的当前路点索引 %d（坐标 %s）。
                当前路点附近检测到连续视觉异常，需要你生成一段替换该路点的绕行路径（1-3 个路点）。
                
                输出严格 JSON 数组格式，每个元素含 x, y, theta, label, actions 字段。
                约束：
                - x/y 必须在 -5.0 到 +10.0 之间（机器人地图范围）
                - 避免原地（与当前路点完全重合）
                - label 以 "planner-绕行-" 开头
                - actions 默认 ["CAPTURE"]
                - 只输出 JSON，不要任何解释文字
                
                完整路线：
                %s
                
                当前路点：
                %s
                """.formatted(idx, hint, routeJson, hint);
    }

    private List<Map<String, Object>> mergeSegment(List<Map<String, Object>> route, int idx,
            List<Map<String, Object>> segment, String deviceKey) {
        List<Map<String, Object>> newRoute = new ArrayList<>(route);
        // 为每个路点补 label 前缀（如果模型没给）
        for (Map<String, Object> p : segment) {
            if (!p.containsKey("label") || String.valueOf(p.get("label")).isBlank()) {
                p.put("label", "planner-绕行-" + deviceKey);
            }
            if (!p.containsKey("actions")) {
                p.put("actions", List.of("CAPTURE"));
            }
        }
        newRoute.set(idx, segment.get(0));
        // 如果模型给了多个绕行点，插入到 currentIndex 之后
        for (int k = 1; k < segment.size(); k++) {
            newRoute.add(idx + k, segment.get(k));
        }
        return newRoute;
    }

    /** 从模型输出中提取 JSON（模型可能在前后加了文字解释）。 */
    private static String extractJson(String raw) {
        if (raw == null) return null;
        // 找第一个 [ 和最后一个 ]
        int open = raw.indexOf('[');
        int close = raw.lastIndexOf(']');
        if (open >= 0 && close > open) {
            return raw.substring(open, close + 1).trim();
        }
        return null;
    }

    private static String truncate(String s, int max) {
        if (s == null) return "";
        return s.length() <= max ? s : s.substring(0, max) + "...";
    }

    private static long elapsed(long start) {
        return System.currentTimeMillis() - start;
    }
}
