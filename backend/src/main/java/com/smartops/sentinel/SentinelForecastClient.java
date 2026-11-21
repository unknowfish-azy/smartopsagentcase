package com.smartops.sentinel;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * 预测面取数客户端：只读调用 ai-service 的 {@code /api/nn/forecast} 与 {@code /api/nn/forecast-info}。
 *
 * <p>边界与 {@link com.smartops.diagnosis.AgentDiagnosisClient} 一致：<b>任何失败都返回 empty</b>，
 * 不抛异常、不伪造预测结果，由调用方如实标注降级。ai-service 不可达时预测面回到统计降级或 offline，
 * 而不是编造一条"神经网络预测"。</p>
 *
 * <p><b>无内部令牌</b>：{@code /api/nn/*} 是 ai-service 自身的只读能力端点（Postgres 直连的
 * {@code nn.forecast} 工具也走同一端点），不需要 SMARTOPS_INTERNAL_TOKEN。</p>
 */
@Component
public class SentinelForecastClient {

    private static final Logger log = LoggerFactory.getLogger(SentinelForecastClient.class);

    private final ObjectMapper objectMapper;
    private final HttpClient client;
    private final String baseUrl;
    private final Duration timeout;

    public SentinelForecastClient(
            ObjectMapper objectMapper,
            @Value("${smartops.agent.trigger.ai-service-url:http://localhost:8001}") String baseUrl,
            @Value("${smartops.sentinel.forecast.timeout-seconds:10}") long timeoutSeconds
    ) {
        this.objectMapper = objectMapper;
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        this.baseUrl = baseUrl == null ? "" : baseUrl.replaceAll("/+$", "");
        this.timeout = Duration.ofSeconds(Math.max(1, timeoutSeconds));
    }

    /** 模型状态；网络失败、超时或非 2xx 一律 empty。 */
    public java.util.Optional<Map<String, Object>> modelInfo() {
        return get("/api/nn/forecast-info");
    }

    /** 单指标多步预测；同样 fail-soft。 */
    public java.util.Optional<Map<String, Object>> forecast(Map<String, Object> payload) {
        try {
            String body = objectMapper.writeValueAsString(payload);
            HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl + "/api/nn/forecast"))
                    .timeout(timeout)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                log.warn("sentinel_forecast.upstream_failed status={} body={}",
                        response.statusCode(), truncate(response.body(), 300));
                return java.util.Optional.empty();
            }
            return java.util.Optional.ofNullable(objectMapper.readValue(
                    response.body(), new TypeReference<Map<String, Object>>() { }));
        } catch (Exception failure) {
            log.warn("sentinel_forecast.call_failed reason={}", failure.toString());
            return java.util.Optional.empty();
        }
    }

    private java.util.Optional<Map<String, Object>> get(String path) {
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl + path))
                    .timeout(timeout)
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                log.warn("sentinel_forecast.info_failed status={}", response.statusCode());
                return java.util.Optional.empty();
            }
            return java.util.Optional.ofNullable(objectMapper.readValue(
                    response.body(), new TypeReference<Map<String, Object>>() { }));
        } catch (Exception failure) {
            log.warn("sentinel_forecast.info_call_failed reason={}", failure.toString());
            return java.util.Optional.empty();
        }
    }

    /** 把 ai-service 的 {@code mode/model_status} 归一成前端契约里的 kind。 */
    static String resolveKind(Object mode, Object modelStatus) {
        String status = modelStatus == null ? "" : String.valueOf(modelStatus);
        String actual = mode == null ? "" : String.valueOf(mode);
        if ("ok".equals(status)) {
            if ("patchtst".equals(actual)) return "neural";
            return "statistical";
        }
        if ("fallback".equals(actual) || "linear".equals(actual)) return "statistical";
        return "unavailable";
    }

    static String text(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    static Double number(Object value) {
        if (value instanceof Number numeric) return numeric.doubleValue();
        return null;
    }

    static List<Object> list(Object value) {
        if (value instanceof List<?> items) return List.copyOf(items);
        return List.of();
    }

    private static String truncate(String text, int limit) {
        return text == null || text.length() <= limit ? (text == null ? "" : text) : text.substring(0, limit);
    }
}
