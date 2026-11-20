package com.smartops.radar;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * GitHub Releases 采集器。
 *
 * <p>来源地址支持仓库主页 {@code https://github.com/{owner}/{repo}} 或
 * {@code https://api.github.com/repos/...}。匿名调用受 GitHub 60 次/小时的限制，
 * 配置环境变量 {@code GITHUB_TOKEN} 可提升配额；令牌只读取环境变量，不落库、不回显。</p>
 */
@Component
public class GithubCollector implements RadarCollector {

    private static final int PER_PAGE = 30;
    private static final int MAX_SUMMARY = 2000;
    private static final String ACCEPT = "application/vnd.github+json";

    private final RadarHttpClient http;
    private final ObjectMapper json;

    public GithubCollector(RadarHttpClient http, ObjectMapper json) {
        this.http = http;
        this.json = json;
    }

    @Override
    public String type() {
        return "GITHUB";
    }

    @Override
    public List<CollectedResource> collect(RadarSource source) {
        String api = apiUrl(source.url());
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("X-GitHub-Api-Version", "2022-11-28");
        String token = System.getenv("GITHUB_TOKEN");
        if (token != null && !token.isBlank()) headers.put("Authorization", "Bearer " + token.strip());

        String body;
        try {
            body = http.get(api, ACCEPT, headers);
        } catch (IOException failure) {
            throw new IllegalStateException("GitHub 抓取失败：" + failure.getMessage(), failure);
        }
        JsonNode root;
        try {
            root = json.readTree(body);
        } catch (IOException invalid) {
            throw new IllegalStateException("GitHub 响应无法解析", invalid);
        }
        if (!root.isArray()) {
            String message = root.path("message").asText(null);
            throw new IllegalStateException(message == null ? "GitHub 返回非数组响应" : "GitHub 返回错误：" + message);
        }

        List<CollectedResource> resources = new ArrayList<>();
        for (JsonNode release : root) {
            if (release.path("draft").asBoolean(false)) continue;
            String htmlUrl = release.path("html_url").asText(null);
            String title = firstNonBlank(release.path("name").asText(null), release.path("tag_name").asText(null));
            if (htmlUrl == null || htmlUrl.isBlank() || title == null) continue;
            resources.add(new CollectedResource(
                    release.path("id").asText(null),
                    title,
                    RadarParseSupport.plainText(release.path("body").asText(null), MAX_SUMMARY),
                    htmlUrl,
                    RadarParseSupport.instant(release.path("published_at").asText(null)),
                    null));
        }
        return resources;
    }

    private static String apiUrl(String sourceUrl) {
        URI uri;
        try {
            uri = URI.create(sourceUrl.strip());
        } catch (IllegalArgumentException invalid) {
            throw new IllegalStateException("GitHub 来源地址无效");
        }
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);
        String path = uri.getPath() == null ? "" : uri.getPath();
        if ("api.github.com".equals(host)) {
            return path.endsWith("/releases") ? sourceUrl.strip() : stripTrailingSlash(sourceUrl.strip()) + "/releases?per_page=" + PER_PAGE;
        }
        if ("github.com".equals(host) || "www.github.com".equals(host)) {
            String[] segments = path.split("/");
            if (segments.length >= 3 && !segments[1].isBlank() && !segments[2].isBlank()) {
                return "https://api.github.com/repos/" + segments[1] + "/" + segments[2] + "/releases?per_page=" + PER_PAGE;
            }
        }
        throw new IllegalStateException("GITHUB 来源需为 github.com/{owner}/{repo} 或 api.github.com/repos/...");
    }

    private static String stripTrailingSlash(String value) {
        String trimmed = value;
        while (trimmed.endsWith("/")) trimmed = trimmed.substring(0, trimmed.length() - 1);
        return trimmed;
    }

    private static String firstNonBlank(String first, String second) {
        if (first != null && !first.isBlank()) return first.strip();
        return second != null && !second.isBlank() ? second.strip() : null;
    }
}
