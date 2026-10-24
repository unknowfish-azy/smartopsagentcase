package com.smartops.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.entity.ModelConnection;
import com.smartops.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class ModelProviderClient {

    private final ObjectMapper objectMapper;
    private final HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

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

        try {
            HttpRequest httpRequest = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(connection.getTimeoutSeconds()))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(payload)))
                    .build();
            HttpResponse<String> response = client.send(
                    httpRequest, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new BusinessException(502,
                        "模型服务调用失败（HTTP " + response.statusCode() + "）");
            }

            Map<String, Object> body = objectMapper.readValue(
                    response.body(), new TypeReference<>() {});
            String content = extractContent(body);
            Map<String, Object> usage = body.get("usage") instanceof Map<?, ?> raw
                    ? objectMapper.convertValue(raw, new TypeReference<>() {})
                    : Map.of();
            return ModelInvocationResponse.builder()
                    .connectionId(connection.getId())
                    .provider(connection.getProvider())
                    .model(connection.getModelName())
                    .content(content)
                    .usage(usage)
                    .build();
        } catch (BusinessException ex) {
            throw ex;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new BusinessException(502, "模型服务调用被中断");
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
