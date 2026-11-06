package com.smartops.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.entity.ModelConnection;
import com.smartops.exception.BusinessException;
import com.smartops.security.OutboundUrlPolicy;
import com.smartops.security.PinnedDns;
import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.CloseableHttpResponse;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.http.io.entity.StringEntity;
import org.apache.hc.core5.util.Timeout;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 模型供应商出站客户端。
 *
 * <p>SEC-14：建连必须落在 {@link OutboundUrlPolicy} 校验过的地址上。Java 17 的
 * {@code java.net.http} 没有解析钩子，因此改用 Apache HttpClient 5 +
 * fail-closed 的 {@link PinnedDns} 解析器：未登记 pin 的主机一律解析失败，
 * 关闭"校验后改 DNS 应答"的 rebinding 窗口。pin 由调用方（ModelConnectionService）
 * 在出站前登记、调用结束后清除。</p>
 *
 * <p>不跟随重定向、不自动重试，避免把 POST 转发到未校验目标或重复计费。</p>
 */
@Service
public class ModelProviderClient {

    private static final int CONNECT_TIMEOUT_SECONDS = 10;

    private final ObjectMapper objectMapper;
    private final CloseableHttpClient client;

    public ModelProviderClient(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        PoolingHttpClientConnectionManager connections = PoolingHttpClientConnectionManagerBuilder.create()
                .setDnsResolver(new org.apache.hc.client5.http.DnsResolver() {
                    @Override
                    public java.net.InetAddress[] resolve(String host) throws java.net.UnknownHostException {
                        return PinnedDns.resolve(host);
                    }

                    @Override
                    public String resolveCanonicalHostname(String host) throws java.net.UnknownHostException {
                        PinnedDns.resolve(host);
                        return host;
                    }
                })
                .setDefaultConnectionConfig(ConnectionConfig.custom()
                        .setConnectTimeout(Timeout.ofSeconds(CONNECT_TIMEOUT_SECONDS))
                        .build())
                .setMaxConnTotal(8)
                .setMaxConnPerRoute(4)
                .build();
        this.client = HttpClients.custom()
                .setConnectionManager(connections)
                .disableRedirectHandling()
                .disableAutomaticRetries()
                .build();
    }

    public ModelInvocationResponse invoke(
            ModelConnection connection,
            String apiKey,
            ModelInvocationRequest request
    ) {
        URI endpoint = endpoint(connection.getBaseUrl());
        List<Map<String, String>> messages = new ArrayList<>();
        if (request.getSystemPrompt() != null && !request.getSystemPrompt().isBlank()) {
            messages.add(Map.of("role", "system", "content", request.getSystemPrompt()));
        }
        messages.add(Map.of("role", "user", "content", request.getPrompt()));

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("model", connection.getModelName());
        payload.put("messages", messages);
        payload.put("temperature", request.getTemperature() == null ? 0.2 : request.getTemperature());

        int timeoutSeconds = connection.getTimeoutSeconds() == null ? 60 : connection.getTimeoutSeconds();
        try {
            HttpPost httpRequest = new HttpPost(endpoint);
            httpRequest.setConfig(RequestConfig.custom()
                    .setConnectionRequestTimeout(Timeout.ofSeconds(Math.min(timeoutSeconds, CONNECT_TIMEOUT_SECONDS)))
                    .setResponseTimeout(Timeout.ofSeconds(timeoutSeconds))
                    .build());
            httpRequest.setHeader("Authorization", "Bearer " + apiKey);
            httpRequest.setEntity(new StringEntity(
                    objectMapper.writeValueAsString(payload), ContentType.APPLICATION_JSON));
            try (CloseableHttpResponse response = client.execute(httpRequest)) {
                int status = response.getCode();
                String body = response.getEntity() == null ? ""
                        : EntityUtils.toString(response.getEntity(), StandardCharsets.UTF_8);
                if (status < 200 || status >= 300) {
                    throw new BusinessException(502,
                            "模型服务调用失败（HTTP " + status + "）");
                }

                Map<String, Object> responseBody = objectMapper.readValue(
                        body, new TypeReference<>() {});
                String content = extractContent(responseBody);
                Map<String, Object> usage = responseBody.get("usage") instanceof Map<?, ?> raw
                        ? objectMapper.convertValue(raw, new TypeReference<>() {})
                        : Map.of();
                return ModelInvocationResponse.builder()
                        .connectionId(connection.getId())
                        .provider(connection.getProvider())
                        .model(connection.getModelName())
                        .content(content)
                        .usage(usage)
                        .build();
            }
        } catch (BusinessException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new BusinessException(502, "模型服务调用失败");
        }
    }

    private URI endpoint(String baseUrl) {
        URI base;
        try {
            base = URI.create(baseUrl);
        } catch (IllegalArgumentException ex) {
            throw new BusinessException("模型 Base URL 无效");
        }
        if (!("https".equalsIgnoreCase(base.getScheme())
                || "http".equalsIgnoreCase(base.getScheme())) || base.getHost() == null) {
            throw new BusinessException("模型 Base URL 只允许 HTTP/HTTPS");
        }
        return URI.create(baseUrl.replaceAll("/+$", "") + "/chat/completions");
    }

    @SuppressWarnings("unchecked")
    private String extractContent(Map<String, Object> body) {
        Object choices = body.get("choices");
        if (!(choices instanceof List<?> list) || list.isEmpty()) {
            return "";
        }
        Object first = list.get(0);
        if (!(first instanceof Map<?, ?> choice)) {
            return "";
        }
        Object message = choice.get("message");
        if (!(message instanceof Map<?, ?> messageMap)) {
            return "";
        }
        Object content = messageMap.get("content");
        return content == null ? "" : String.valueOf(content);
    }
}
