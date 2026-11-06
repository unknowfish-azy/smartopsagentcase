package com.smartops.sentinel;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.http.HttpHeaders;
import org.springframework.web.client.RestClient;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * 外部告警平台（Alertmanager）静默窗口的真实写入。
 *
 * <p>口径：未配置地址时返回 {@code null}，调用方必须把结果记为 {@code NOT_CONFIGURED}，
 * 而不是"同步成功"。调用失败直接抛异常，由调用方如实记录 {@code FAILED}。</p>
 */
@Component
public class AlertmanagerSilenceClient {

    private final RestClient restClient = RestClient.create();
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final String baseUrl;
    private final String token;

    public AlertmanagerSilenceClient(
            @Value("${smartops.alerts.alertmanager.url:}") String baseUrl,
            @Value("${smartops.alerts.alertmanager.token:}") String token) {
        this.baseUrl = baseUrl == null ? "" : baseUrl.trim();
        this.token = token == null ? "" : token.trim();
    }

    /** 是否配置了外部平台；false 表示只能本地静默，不能对外声称已同步。 */
    public boolean configured() {
        return !baseUrl.isEmpty();
    }

    /**
     * 建立外部静默，返回外部 ID。
     *
     * <p>GLOBAL 使用正则匹配全部告警，TASK 只匹配同一任务的 alertname 维度。</p>
     */
    public String create(String scope, Long scopeId, Instant startsAt, Instant endsAt,
                         String reason, String createdBy) {
        requireConfigured();
        Map<String, Object> matcher = "GLOBAL".equals(scope)
                ? Map.of("name", "smartops_scope", "value", ".*", "isRegex", true, "isEqual", true)
                : Map.of("name", "smartops_task", "value", String.valueOf(scopeId), "isRegex", false, "isEqual", true);
        Map<String, Object> body = Map.of(
                "matchers", List.of(matcher),
                "startsAt", startsAt.toString(),
                "endsAt", endsAt.toString(),
                "createdBy", createdBy,
                "comment", reason);
        JsonNode response = restClient.post()
                .uri(baseUrl + "/api/v2/silences")
                .headers(headers -> applyToken(headers))
                .body(body)
                .retrieve()
                .body(JsonNode.class);
        String id = response == null ? "" : response.path("silenceID").asText("");
        if (id.isBlank()) {
            throw new IllegalStateException("外部平台未返回 silenceID");
        }
        return id;
    }

    /** 撤销外部静默；外部失败必须抛出，不能让本地误以为已撤销。 */
    public void expire(String externalId) {
        requireConfigured();
        restClient.delete()
                .uri(baseUrl + "/api/v2/silence/" + externalId)
                .headers(headers -> applyToken(headers))
                .retrieve()
                .toBodilessEntity();
    }

    void applyToken(HttpHeaders headers) {
        if (!token.isEmpty()) {
            headers.setBearerAuth(token);
        }
    }

    private void requireConfigured() {
        if (!configured()) {
            throw new IllegalStateException("未配置 smartops.alerts.alertmanager.url");
        }
    }
}
