package com.smartops.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.UUID;
import java.util.function.Function;
import java.util.regex.Pattern;

@Service
public class HarborCatalogService {
    private static final int PAGE_SIZE = 20;
    private static final int MAX_BYTES = 1_048_576;
    private static final Pattern PROJECT_NAME = Pattern.compile("[a-z0-9][a-z0-9._-]{0,127}");
    private final ObjectMapper json;
    private final OperationRunRecorder recorder;
    private final String url;
    private final String username;
    private final String secret;

    public HarborCatalogService(ObjectMapper json, OperationRunRecorder recorder,
            @Value("${smartops.harbor.url:}") String url,
            @Value("${smartops.harbor.username:}") String username,
            @Value("${smartops.harbor.secret:}") String secret) {
        this.json = json;
        this.recorder = recorder;
        this.url = url.trim();
        this.username = username;
        this.secret = secret;
    }

    public SourceStatus status() {
        return new SourceStatus(!url.isBlank(), !username.isBlank() && !secret.isBlank());
    }

    public ConnectionCheck checkConnection(Long userId) {
        if (url.isBlank()) return new ConnectionCheck("UNCONFIGURED", "尚未配置 Harbor", Instant.now(), null);
        try {
            var result = listProjects(userId, 1);
            return new ConnectionCheck("READABLE", "当前凭据可读取项目；不代表所有组件健康", Instant.now(), result.traceId());
        } catch (HarborFailure failure) {
            return new ConnectionCheck(failure.category, failure.getMessage(), Instant.now(), failure.traceId);
        } catch (BusinessException failure) {
            return new ConnectionCheck("CONFIGURATION", "请检查 Harbor 地址和凭据配置", Instant.now(), null);
        }
    }

    public Page<Artifact> listArtifacts(Long userId, String project, String repository, int page) {
        if (project == null || !PROJECT_NAME.matcher(project).matches()
                || repository == null || repository.length() > 255
                || !repository.matches("[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*"))
            throw new BusinessException(400, "项目或仓库名称不符合 Harbor 命名规则");
        return query(userId, "/api/v2.0/projects/" + project + "/repositories/"
                + repository.replace("/", "%252F") + "/artifacts", page, "artifacts", node -> {
            List<String> tags = new ArrayList<>();
            node.path("tags").forEach(tag -> tags.add(tag.path("name").asText()));
            List<String> platforms = new ArrayList<>();
            String os = node.path("extra_attrs").path("os").asText();
            String architecture = node.path("extra_attrs").path("architecture").asText();
            if (!os.isBlank() && !architecture.isBlank()) platforms.add(os + "/" + architecture);
            node.path("references").forEach(reference -> {
                var platform = reference.path("platform");
                if (!platform.path("os").asText().isBlank() && !platform.path("architecture").asText().isBlank())
                    platforms.add(platform.path("os").asText() + "/" + platform.path("architecture").asText());
            });
            return new Artifact(node.path("digest").asText(), List.copyOf(tags), node.path("size").asLong(),
                    node.path("type").asText(), node.path("push_time").asText(), platforms.stream().distinct().toList());
        });
    }

    public Page<Project> listProjects(Long userId, int page) {
        return query(userId, "/api/v2.0/projects", page, "projects", node ->
                new Project(node.path("name").asText(),
                        "true".equalsIgnoreCase(node.path("metadata").path("public").asText()),
                        node.path("repo_count").asInt(0)));
    }

    public Page<Repository> listRepositories(Long userId, String project, int page) {
        if (project == null || !PROJECT_NAME.matcher(project).matches())
            throw new BusinessException(400, "项目名称不符合 Harbor 命名规则");
        return query(userId, "/api/v2.0/projects/" + project + "/repositories", page,
                "repositories", node -> new Repository(node.path("name").asText(),
                        node.path("artifact_count").asInt(0)));
    }

    private <T> Page<T> query(Long userId, String path, int page, String action, Function<JsonNode, T> mapper) {
        if (page < 1 || page > 10_000) throw new BusinessException(400, "页码需在 1–10000 之间");
        if (url.isBlank()) throw new BusinessException(503, "Harbor 地址尚未配置");
        if (username.isBlank() != secret.isBlank() || username.contains(":"))
            throw new BusinessException(503, "Harbor 凭据配置不完整");
        URI endpoint = URI.create(base().toString().replaceAll("/+$", "")
                + path + "?page=" + page + "&page_size=" + PAGE_SIZE);
        String traceId = UUID.randomUUID().toString();
        Instant started = Instant.now();
        var run = recorder.start(traceId, userId, new HarborIdentity(userId), "harbor-" + action, started);
        String description = "Harbor " + action + " read-only page=" + page + " target=" + path;
        FetchResult fetched;
        List<T> items = new ArrayList<>();
        try {
            fetched = fetch(endpoint);
            fetched.items().forEach(node -> {
                if (!node.isObject()) throw new HarborFailure(502, "INVALID_RESPONSE", "Harbor 列表条目格式异常");
                items.add(mapper.apply(node));
            });
        } catch (RuntimeException ex) {
            if (ex instanceof HarborFailure failure) failure.traceId = traceId;
            Instant failed = Instant.now();
            recorder.recordCommand(run, 1, description, 1, "", "Harbor 查询失败；原始响应不持久化", started, failed);
            recorder.finish(run, "FAILED", failed);
            throw ex;
        }
        Instant finished = Instant.now();
        recorder.recordCommand(run, 1, description, 0, "返回 " + items.size() + " 条；原始响应不持久化", "", started, finished);
        recorder.finish(run, "SUCCEEDED", finished);
        return new Page<>(List.copyOf(items), fetched.total(), page, PAGE_SIZE, traceId);
    }

    private FetchResult fetch(URI endpoint) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) endpoint.toURL().openConnection();
            connection.setConnectTimeout(3000);
            connection.setReadTimeout(5000);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("Accept", "application/json");
            if (!username.isBlank()) {
                String value = Base64.getEncoder().encodeToString((username + ":" + secret).getBytes(StandardCharsets.UTF_8));
                connection.setRequestProperty("Authorization", "Basic " + value);
            }
            int status = connection.getResponseCode();
            if (status != 200) throw new HarborFailure(502, switch (status) {
                case 401 -> "AUTHENTICATION";
                case 403 -> "AUTHORIZATION";
                case 429 -> "RATE_LIMIT";
                default -> "UPSTREAM";
            }, "Harbor 返回 HTTP " + status + "，请检查地址和读取权限");
            byte[] bytes;
            try (var body = connection.getInputStream()) { bytes = body.readNBytes(MAX_BYTES + 1); }
            if (bytes.length > MAX_BYTES) throw new HarborFailure(502, "INVALID_RESPONSE", "Harbor 返回超过 1 MiB，请缩小查询范围");
            JsonNode response = json.readTree(bytes);
            if (response == null || !response.isArray()) throw new HarborFailure(502, "INVALID_RESPONSE", "Harbor 未返回列表数据");
            int total = response.size();
            String totalHeader = connection.getHeaderField("X-Total-Count");
            if (totalHeader != null) {
                try { total = Math.max(response.size(), Integer.parseInt(totalHeader)); }
                catch (NumberFormatException ignored) { total = response.size(); }
            }
            return new FetchResult(response, total);
        } catch (BusinessException ex) { throw ex; }
        catch (java.net.SocketTimeoutException ex) { throw new HarborFailure(504, "TIMEOUT", "Harbor 连接或读取超时"); }
        catch (javax.net.ssl.SSLException ex) { throw new HarborFailure(502, "TLS", "Harbor TLS 校验失败，请检查证书及信任链"); }
        catch (com.fasterxml.jackson.core.JsonProcessingException ex) { throw new HarborFailure(502, "INVALID_RESPONSE", "Harbor 返回无法解析的列表数据"); }
        catch (java.io.IOException ex) { throw new HarborFailure(502, "NETWORK", "无法读取 Harbor，请检查网络连接"); }
        catch (Exception ex) { throw new HarborFailure(502, "UPSTREAM", "无法读取 Harbor，请检查 API 配置"); }
        finally { if (connection != null) connection.disconnect(); }
    }

    private URI base() {
        try {
            URI uri = URI.create(url);
            if (!("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())) || uri.getHost() == null
                    || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null)
                throw new IllegalArgumentException();
            return uri;
        } catch (IllegalArgumentException ex) { throw new BusinessException(503, "Harbor URL 配置无效"); }
    }

    private record FetchResult(JsonNode items, int total) {}
    public record SourceStatus(boolean configured, boolean credentialsConfigured) {}
    public record Page<T>(List<T> items, int total, int page, int pageSize, String traceId) {}
    public record Project(String name, boolean publicAccess, int repositoryCount) {}
    public record Repository(String name, int artifactCount) {}
    public record Artifact(String digest, List<String> tags, long size, String type, String pushedAt, List<String> platforms) {}
    public record ConnectionCheck(String state, String message, Instant checkedAt, String traceId) {}

    private static final class HarborFailure extends BusinessException {
        private final String category;
        private String traceId;
        private HarborFailure(int code, String category, String message) {
            super(code, message);
            this.category = category;
        }
    }

    private record HarborIdentity(Long userId) implements OperationRuntime {
        public String id() { return "harbor:catalog"; }
        public Long sessionId() { return null; }
        public boolean isOpen() { return false; }
        public void write(String input) { throw new UnsupportedOperationException(); }
        public void resize(int columns, int rows) { throw new UnsupportedOperationException(); }
        public void onOutput(OutputListener listener) { throw new UnsupportedOperationException(); }
        public void close() {}
    }
}
