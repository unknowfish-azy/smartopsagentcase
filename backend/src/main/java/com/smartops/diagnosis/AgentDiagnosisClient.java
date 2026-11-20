package com.smartops.diagnosis;

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
import java.util.Map;
import java.util.Optional;

/**
 * W7：把告警上下文交给 ai-service 做只读初诊。
 *
 * <p>调用只带内部令牌，不使用任何浏览器会话；ai-service 侧同样 fail-closed 校验。
 * 初诊是增强项：网络失败、超时或非 2xx 一律返回 empty，由调用方记 WARN，
 * 绝不影响告警主链路，也绝不伪造结论。</p>
 */
@Slf4j
@Component
public class AgentDiagnosisClient {

    private static final String TRIGGER_PATH = "/api/agent/trigger";

    private final ObjectMapper objectMapper;
    private final HttpClient client;
    private final String baseUrl;
    private final String internalToken;
    private final Duration timeout;

    public AgentDiagnosisClient(
            ObjectMapper objectMapper,
            @Value("${smartops.agent.trigger.ai-service-url:http://localhost:8001}") String baseUrl,
            @Value("${smartops.security.internal-token:}") String internalToken,
            @Value("${smartops.agent.trigger.timeout-seconds:30}") long timeoutSeconds
    ) {
        this.objectMapper = objectMapper;
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        this.baseUrl = baseUrl == null ? "" : baseUrl.replaceAll("/+$", "");
        this.internalToken = internalToken == null ? "" : internalToken;
        this.timeout = Duration.ofSeconds(Math.max(1, timeoutSeconds));
    }

    /** 发起一次只读初诊；任何失败都返回 empty（不抛异常）。 */
    public Optional<Map<String, Object>> diagnose(Map<String, Object> payload) {
        if (internalToken.isBlank()) {
            log.warn("agent_trigger.not_configured reason=SMARTOPS_INTERNAL_TOKEN_MISSING");
            return Optional.empty();
        }
        try {
            String body = objectMapper.writeValueAsString(payload);
            HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl + TRIGGER_PATH))
                    .timeout(timeout)
                    .header("Content-Type", "application/json")
                    .header("X-SmartOps-Internal-Token", internalToken)
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                log.warn("agent_trigger.upstream_failed status={} body={}",
                        response.statusCode(), truncate(response.body(), 300));
                return Optional.empty();
            }
            return Optional.ofNullable(objectMapper.readValue(
                    response.body(), new TypeReference<Map<String, Object>>() { }));
        } catch (Exception failure) {
            // 初诊是增强项：任何失败都只降级，不影响告警主链路。
            log.warn("agent_trigger.call_failed reason={}", failure.toString());
            return Optional.empty();
        }
    }

    private static String truncate(String text, int limit) {
        if (text == null) return "";
        return text.length() <= limit ? text : text.substring(0, limit);
    }
}
