package com.smartops.radar;

import com.smartops.security.OutboundUrlPolicy;
import com.smartops.security.PinnedDns;
import jakarta.annotation.PreDestroy;
import org.apache.hc.client5.http.classic.methods.HttpGet;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.CloseableHttpResponse;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.stereotype.Component;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * 资源雷达专用出站客户端。
 *
 * <p>与知识爬取保持同一条安全链：逐跳 {@link OutboundUrlPolicy} 校验 + 连接期
 * {@link PinnedDns} pin + 响应体下载上限，禁止重定向自动跳转与自动重试。
 * 采集器只能通过这里发起请求，不允许自行 new HttpClient。</p>
 */
@Component
public class RadarHttpClient {

    private static final String USER_AGENT = "SmartOpsAgent-ResourceRadar/1.0";
    private static final long MAX_DOWNLOAD_BYTES = 5L * 1024 * 1024;
    private static final int MAX_REDIRECTS = 4;

    private final CloseableHttpClient client;

    public RadarHttpClient() {
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
                .setDefaultConnectionConfig(ConnectionConfig.custom().setConnectTimeout(Timeout.ofSeconds(8)).build())
                .setMaxConnTotal(4)
                .setMaxConnPerRoute(4)
                .build();
        this.client = HttpClients.custom()
                .setConnectionManager(connections)
                .disableRedirectHandling()
                .disableAutomaticRetries()
                .setDefaultRequestConfig(RequestConfig.custom()
                        .setConnectionRequestTimeout(Timeout.ofSeconds(8))
                        .setResponseTimeout(Timeout.ofSeconds(10))
                        .build())
                .setUserAgent(USER_AGENT)
                .build();
    }

    /**
     * 发起一次受限 GET，返回响应体文本。
     *
     * @throws IOException 目标被出站策略拒绝、非 2xx、超过下载上限或网络失败
     */
    public String get(String url, String accept, Map<String, String> headers) throws IOException {
        String current = url;
        for (int hop = 0; hop < MAX_REDIRECTS; hop++) {
            URI uri;
            try {
                uri = URI.create(current);
            } catch (IllegalArgumentException invalid) {
                throw new IOException("地址无效");
            }
            OutboundUrlPolicy.Decision decision = OutboundUrlPolicy.inspect(uri);
            if (!decision.allowed()) {
                throw new IOException("目标地址不允许访问（" + decision.rule() + "）");
            }
            PinnedDns.pin(uri.getHost(), decision.addresses());
            HttpGet request = new HttpGet(uri);
            request.setHeader("User-Agent", USER_AGENT);
            if (accept != null) request.setHeader("Accept", accept);
            if (headers != null) headers.forEach(request::setHeader);
            try (CloseableHttpResponse response = client.execute(request)) {
                int code = response.getCode();
                String location = headerValue(response, "Location");
                if (code >= 200 && code < 300) {
                    long declared = declaredLength(response);
                    if (declared > MAX_DOWNLOAD_BYTES) throw new IOException("响应体超过下载上限");
                    try (InputStream body = response.getEntity() != null ? response.getEntity().getContent() : null) {
                        return readBounded(body);
                    }
                }
                if (code >= 300 && code < 400 && location != null) {
                    current = uri.resolve(location).toString();
                    continue;
                }
                throw new IOException("HTTP " + code);
            } finally {
                PinnedDns.clear(uri.getHost());
            }
        }
        throw new IOException("重定向次数过多");
    }

    @PreDestroy
    void close() throws IOException {
        client.close();
    }

    private static long declaredLength(CloseableHttpResponse response) {
        String header = headerValue(response, "Content-Length");
        if (header == null) return -1L;
        try {
            return Long.parseLong(header.trim());
        } catch (NumberFormatException ignored) {
            return -1L;
        }
    }

    private static String headerValue(CloseableHttpResponse response, String name) {
        try {
            var header = response.getHeader(name);
            return header == null ? null : header.getValue();
        } catch (org.apache.hc.core5.http.ProtocolException invalid) {
            return null;
        }
    }

    private static String readBounded(InputStream body) throws IOException {
        if (body == null) return "";
        ByteArrayOutputStream collected = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int read;
        while ((read = body.read(buffer)) != -1) {
            if (collected.size() + (long) read > MAX_DOWNLOAD_BYTES) {
                throw new IOException("响应体超过下载上限");
            }
            collected.write(buffer, 0, read);
        }
        return collected.toString(StandardCharsets.UTF_8);
    }
}
