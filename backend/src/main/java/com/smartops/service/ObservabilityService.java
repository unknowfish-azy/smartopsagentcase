package com.smartops.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Fixed administrator-configured endpoints; browser input never selects a host. */
@Service
public class ObservabilityService {
    private static final int MAX_BYTES = 1_048_576;
    private final ObjectMapper json;
    private final OperationRunRecorder recorder;
    private final Map<String, Source> sources;

    public ObservabilityService(ObjectMapper json, OperationRunRecorder recorder,
            @Value("${smartops.observability.prometheus-url:}") String prometheusUrl,
            @Value("${smartops.observability.prometheus-token:}") String prometheusToken,
            @Value("${smartops.observability.loki-url:}") String lokiUrl,
            @Value("${smartops.observability.loki-token:}") String lokiToken) {
        this.json = json;
        this.recorder = recorder;
        this.sources = Map.of("prometheus", new Source(prometheusUrl, prometheusToken),
                "loki", new Source(lokiUrl, lokiToken));
    }

    public List<SourceStatus> sources() {
        return List.of(status("prometheus"), status("loki"));
    }

    private SourceStatus status(String id) {
        Source s = sources.get(id);
        return new SourceStatus(id, !s.url().isBlank(), !s.token().isBlank());
    }

    public QueryResult query(Long userId, String id, String query, int minutes, int limit) {
        Source source = sources.get(id);
        if (source == null) throw new BusinessException(404, "未知观测数据源");
        if (query == null || query.isBlank() || query.length() > 2000 || minutes < 1 || minutes > 60 || limit < 1 || limit > 500)
            throw new BusinessException(400, "查询需为 1–2000 字符，范围 1–60 分钟，条数 1–500");
        if (source.url().isBlank()) throw new BusinessException(503, "该数据源尚未配置，请设置后端观测数据源环境变量");
        URI base = base(source.url());
        Instant end = Instant.now();
        Instant start = end.minusSeconds(minutes * 60L);
        String path = id.equals("prometheus") ? "/api/v1/query_range" : "/loki/api/v1/query_range";
        String params = "query=" + URLEncoder.encode(query, StandardCharsets.UTF_8)
                + "&start=" + start.getEpochSecond() + "&end=" + end.getEpochSecond();
        if (id.equals("prometheus")) params += "&step=" + Math.max(15, minutes * 6) + "&timeout=5s";
        else params += "&limit=" + limit + "&direction=backward";
        URI endpoint = URI.create(base.toString().replaceAll("/+$", "") + path + "?" + params);
        String trace = UUID.randomUUID().toString();
        var run = recorder.start(trace, userId, new SourceIdentity(id, userId), "observability-" + id, end);
        // Do not persist credentials, raw LogQL/PromQL, or raw log lines.
        String description = id + " read-only range=" + minutes + "m limit=" + limit;
        JsonNode result;
        try {
            result = fetch(endpoint, source.token());
        } catch (RuntimeException ex) {
            Instant failed = Instant.now();
            recorder.recordCommand(run, 1, description, 1, "", "观测查询失败；详细错误已返回调用者", end, failed);
            recorder.finish(run, "FAILED", failed);
            throw ex;
        }
        Instant finished = Instant.now();
        recorder.recordCommand(run, 1, description, 0, "上游 status=success；原始内容不写入审计", "", end, finished);
        recorder.finish(run, "SUCCEEDED", finished);
        return new QueryResult(trace, id, start, end, result);
    }

    private JsonNode fetch(URI endpoint, String token) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) endpoint.toURL().openConnection();
            connection.setConnectTimeout(3000);
            connection.setReadTimeout(5000);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("Accept", "application/json");
            if (!token.isBlank()) connection.setRequestProperty("Authorization", "Bearer " + token);
            int status = connection.getResponseCode();
            if (status != 200) throw new BusinessException(502, "观测服务返回 HTTP " + status + "，请检查数据源地址、授权和查询语法");
            byte[] bytes;
            try (var body = connection.getInputStream()) { bytes = body.readNBytes(MAX_BYTES + 1); }
            if (bytes.length > MAX_BYTES) throw new BusinessException(502, "观测结果超过 1 MiB，请缩小查询范围");
            JsonNode response = json.readTree(bytes);
            if (response == null || !"success".equals(response.path("status").asText()) || !response.has("data"))
                throw new BusinessException(502, "观测服务未返回有效成功结果，请检查查询语法及接口地址");
            return response;
        } catch (BusinessException ex) { throw ex; }
        catch (java.net.SocketTimeoutException ex) { throw new BusinessException(504, "观测服务连接或读取超时"); }
        catch (Exception ex) { throw new BusinessException(502, "无法读取观测服务，请检查网络、证书及 JSON 响应"); }
        finally { if (connection != null) connection.disconnect(); }
    }

    private URI base(String url) {
        try {
            URI uri = URI.create(url.trim());
            if (!("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())) || uri.getHost() == null
                    || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null)
                throw new IllegalArgumentException();
            return uri;
        } catch (IllegalArgumentException ex) { throw new BusinessException(503, "后端数据源 URL 配置无效"); }
    }

    private record Source(String url, String token) {}
    public record SourceStatus(String id, boolean configured, boolean tokenConfigured) {}
    public record QueryResult(String traceId, String source, Instant start, Instant end, JsonNode response) {}

    /** Identity for existing audit storage, not a shell or an active remote session. */
    private record SourceIdentity(String source, Long userId) implements OperationRuntime {
        public String id() { return "observability:" + source; }
        public Long sessionId() { return null; }
        public boolean isOpen() { return false; }
        public void write(String input) { throw new UnsupportedOperationException(); }
        public void resize(int columns, int rows) { throw new UnsupportedOperationException(); }
        public void onOutput(OutputListener listener) { throw new UnsupportedOperationException(); }
        public void close() {}
    }
}
