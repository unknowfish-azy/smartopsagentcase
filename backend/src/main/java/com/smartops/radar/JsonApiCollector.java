package com.smartops.radar;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * 通用 JSON API 采集器。
 *
 * <p>P1 不引入每源字段映射配置，按常见字段名做只读适配：根数组，或
 * {@code items/data/results/list/entries/posts} 下的数组。字段对不上就跳过该条，
 * 不猜测、不补造；缺 URL 或标题的条目不进入雷达。</p>
 */
@Component
public class JsonApiCollector implements RadarCollector {

    private static final int MAX_ITEMS = 100;
    private static final int MAX_SUMMARY = 2000;
    private static final String ACCEPT = "application/json, application/*+json;q=0.9";
    private static final List<String> ARRAY_FIELDS =
            List.of("items", "data", "results", "list", "entries", "posts", "releases", "records");
    private static final List<String> NESTED_ARRAY_FIELDS = List.of("items", "list", "results", "rows", "records");

    private final RadarHttpClient http;
    private final ObjectMapper json;

    public JsonApiCollector(RadarHttpClient http, ObjectMapper json) {
        this.http = http;
        this.json = json;
    }

    @Override
    public String type() {
        return "JSON_API";
    }

    @Override
    public List<CollectedResource> collect(RadarSource source) {
        String body;
        try {
            body = http.get(source.url(), ACCEPT, null);
        } catch (IOException failure) {
            throw new IllegalStateException("JSON 抓取失败：" + failure.getMessage(), failure);
        }
        JsonNode root;
        try {
            root = json.readTree(body);
        } catch (IOException invalid) {
            throw new IllegalStateException("JSON 响应无法解析", invalid);
        }
        JsonNode array = locateArray(root);
        if (array == null) {
            throw new IllegalStateException("JSON 中未找到条目数组（支持根数组或 items/data/results/list/entries/posts 字段）");
        }
        List<CollectedResource> resources = new ArrayList<>();
        for (JsonNode node : array) {
            if (resources.size() >= MAX_ITEMS) break;
            if (!node.isObject()) continue;
            String title = text(node, "title", "name", "headline", "subject");
            String url = text(node, "url", "link", "html_url", "permalink", "detail_url");
            if (title == null || url == null) continue;
            if (!url.startsWith("http://") && !url.startsWith("https://")) continue;
            String summary = text(node, "summary", "description", "desc", "content", "excerpt");
            resources.add(new CollectedResource(
                    text(node, "id", "guid", "uuid", "slug"),
                    title,
                    RadarParseSupport.plainText(summary, MAX_SUMMARY),
                    url,
                    instant(node, "published_at", "publishedAt", "published", "pubDate", "date", "created_at", "createdAt"),
                    instant(node, "expires_at", "expiresAt", "expires", "end_date", "deadline")));
        }
        return resources;
    }

    private static JsonNode locateArray(JsonNode root) {
        if (root == null || root.isNull()) return null;
        if (root.isArray()) return root;
        for (String field : ARRAY_FIELDS) {
            JsonNode candidate = root.get(field);
            if (candidate == null) continue;
            if (candidate.isArray()) return candidate;
            if (candidate.isObject()) {
                for (String nested : NESTED_ARRAY_FIELDS) {
                    JsonNode inner = candidate.get(nested);
                    if (inner != null && inner.isArray()) return inner;
                }
            }
        }
        return null;
    }

    private static String text(JsonNode node, String... fields) {
        for (String field : fields) {
            JsonNode value = node.get(field);
            if (value == null || value.isNull()) continue;
            String text = value.isValueNode() ? value.asText() : null;
            if (text != null && !text.isBlank()) return text.strip();
        }
        return null;
    }

    private static Instant instant(JsonNode node, String... fields) {
        for (String field : fields) {
            JsonNode value = node.get(field);
            if (value == null || value.isNull()) continue;
            if (value.isNumber()) return epoch(value.asLong());
            String text = value.asText(null);
            if (text == null || text.isBlank()) continue;
            String trimmed = text.strip();
            if (trimmed.matches("\\d{9,13}")) return epoch(Long.parseLong(trimmed));
            Instant parsed = RadarParseSupport.instant(trimmed);
            if (parsed != null) return parsed;
        }
        return null;
    }

    private static Instant epoch(long value) {
        if (value <= 0) return null;
        return value > 1_000_000_000_000L ? Instant.ofEpochMilli(value) : Instant.ofEpochSecond(value);
    }
}
