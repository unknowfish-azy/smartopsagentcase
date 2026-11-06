package com.smartops.cloud;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * 基于 JDK HttpClient 的默认传输实现。
 *
 * 单次请求超时由配置控制；不在这里做重试，重试与退避由适配器按错误分类处理。
 */
@Component
public class JdkCloudHttpTransport implements CloudHttpTransport {

    private final HttpClient client;
    private final Duration requestTimeout;

    public JdkCloudHttpTransport(@Value("${smartops.cloud.sync.request-timeout-ms:15000}") long timeoutMs) {
        this.requestTimeout = Duration.ofMillis(Math.max(1000, timeoutMs));
        this.client = HttpClient.newBuilder()
                .connectTimeout(requestTimeout)
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public Response post(String uri, Map<String, String> headers, String body) throws IOException, InterruptedException {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(uri))
                .timeout(requestTimeout)
                .POST(HttpRequest.BodyPublishers.ofString(body == null ? "" : body));
        headers.forEach(builder::header);
        HttpResponse<String> response = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        return new Response(response.statusCode(), response.headers().map(), response.body());
    }

    @Override
    public Response get(String uri, Map<String, String> headers) throws IOException, InterruptedException {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(uri))
                .timeout(requestTimeout)
                .GET();
        headers.forEach(builder::header);
        HttpResponse<String> response = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        return new Response(response.statusCode(), response.headers().map(), response.body());
    }

    static List<String> headerValues(Map<String, List<String>> headers, String name) {
        return headers == null ? List.of() : headers.getOrDefault(name, List.of());
    }
}
