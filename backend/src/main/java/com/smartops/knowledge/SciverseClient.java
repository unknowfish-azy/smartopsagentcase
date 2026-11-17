package com.smartops.knowledge;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * SciverseClient — OpenDataLab SciVerse 科学文献平台 API 客户端
 *
 * 只对接官方公开契约（llms.txt / docs.sciverse.space，2026-11 核对）：
 *  - POST {base}/agentic-search：语义检索正文证据片段（返回 hits[]，含 chunk/doc_id/score）；
 *  - GET  {base}/content?doc_id=...：按 doc_id 分段读取全文（offset/limit 为字符切片）。
 *
 * 安全红线：
 *  - 目标主机固定为配置的 SciVerse 网关（默认 https://api.sciverse.space），
 *    发起前经 OutboundUrlPolicy 校验，SSRF 策略与 KnowledgeCrawlService 一致；
 *  - API Key 走环境变量注入（SMARTOPS_SCIVERSE_API_KEY）或页面「配置密钥」手动写入
 *    （SciverseKeyStore 持久化到 backend/.env.local，重启后经启动脚本重新注入）；
 *    运行期可经 setApiKey 热更新，不落库、不回显完整值；
 *  - 未配置 Key 时调用方收到 SciverseNotConfiguredException，前端降级为引导提示。
 *
 * 说明：解析层对字段名做容错匹配（doc_id/id、text/chunk/snippet 等），
 * 保证平台侧字段命名演进时不需要改代码。
 */
@Service
public class SciverseClient {

    private static final Logger log = LoggerFactory.getLogger(SciverseClient.class);

    /** SciVerse 未配置 API Key 或平台不可用时的业务异常（HTTP 503 语义交给调用方映射）。 */
    public static class SciverseNotConfiguredException extends RuntimeException {
        public SciverseNotConfiguredException(String message) { super(message); }
    }

    /** 一条检索证据：文献定位 + 原文片段。 */
    public record Evidence(String docId, String title, String locator, String text) {}

    private static final String USER_AGENT = "SmartOpsAgent-Knowledge/1.0";
    private final String apiBase;
    /** volatile：允许页面「配置密钥」在运行期热更新，无需重启进程。 */
    private volatile String apiKey;
    private final String searchPath;
    private final String contentPath;
    private final ObjectMapper mapper;
    private final HttpClient http;

    public SciverseClient(
            @Value("${smartops.sciverse.base-url:https://api.sciverse.space}") String apiBase,
            @Value("${smartops.sciverse.api-key:}") String apiKey,
            @Value("${smartops.sciverse.search-path:/agentic-search}") String searchPath,
            @Value("${smartops.sciverse.content-path:/content}") String contentPath,
            ObjectMapper mapper) {
        this.apiBase = apiBase == null ? "" : apiBase.trim();
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.searchPath = searchPath == null || searchPath.isBlank() ? "/agentic-search" : searchPath.trim();
        this.contentPath = contentPath == null || contentPath.isBlank() ? "/content" : contentPath.trim();
        this.mapper = mapper;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(8))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        // 启动即打印实际生效的网关配置：用于一眼确认属性来源（yml / 环境变量 / -D 系统属性）是否解析正确。
        log.info("SCIVERSE effective config: base={} search={} content={} key={}",
                this.apiBase, this.searchPath, this.contentPath,
                this.apiKey.isBlank() ? "MISSING" : "present(" + this.apiKey.length() + " chars)");
    }

    public boolean configured() {
        return !apiKey.isBlank();
    }

    /** 运行期热更新 Key（页面「配置密钥」通道）；只落指纹日志，不落完整值。 */
    public void setApiKey(String newKey) {
        String next = newKey == null ? "" : newKey.trim();
        String before = apiKey.isBlank() ? "MISSING" : "present(" + apiKey.length() + ")";
        this.apiKey = next;
        log.info("SCIVERSE api key updated: {} -> {} (fingerprint={}…{})",
                before,
                next.isBlank() ? "MISSING" : "present(" + next.length() + ")",
                next.length() > 6 ? next.substring(0, 6) : "short",
                next.length() > 4 ? next.substring(next.length() - 4) : "short");
    }

    /** 脱敏预览：前 6 + 尾 4 + 长度，供状态接口展示；Key 为空返回 null。 */
    public String keyPreview() {
        if (apiKey.isBlank()) return null;
        String head = apiKey.substring(0, Math.min(6, apiKey.length()));
        String tail = apiKey.length() > 6 ? apiKey.substring(apiKey.length() - 4) : "";
        return head + "…" + tail + "（" + apiKey.length() + " 字符）";
    }

    /** 仅域名，供状态接口展示；不包含路径与鉴权信息。 */
    public String baseUrl() {
        return apiBase;
    }

    /** 语义检索：query 为蒸馏目标主题，limit 控制返回证据条数。 */
    public List<Evidence> search(String query, int limit) {
        String body = mapper.createObjectNode()
                .put("query", query == null ? "" : query.trim())
                .put("top_k", Math.max(1, Math.min(20, limit)))
                .toString();
        JsonNode root = call("POST", searchPath, body);
        return parseEvidence(root);
    }

    /** 按 doc_id 读取全文（分段拼接），用于证据不足时的原文补全。官方契约：GET /content?doc_id=...（offset/limit 字符切片）。 */
    public String content(String docId) {
        JsonNode root = call("GET", contentPath + "?doc_id=" + encode(docId), null);
        return firstText(root);
    }

    private JsonNode call(String method, String pathWithQuery, String jsonBody) {
        if (!configured()) {
            throw new SciverseNotConfiguredException("SCIVERSE_API_KEY_MISSING");
        }
        URI uri = URI.create(apiBase + pathWithQuery);
        // 与 KnowledgeCrawlService 同一条 SSRF 红线：出站前校验目标地址。
        com.smartops.security.OutboundUrlPolicy.Decision decision = com.smartops.security.OutboundUrlPolicy.inspect(uri);
        if (!decision.allowed()) {
            throw new SciverseNotConfiguredException("SCIVERSE_ENDPOINT_BLOCKED");
        }
        try {
            HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(15))
                    .header("User-Agent", USER_AGENT)
                    .header("Accept", "application/json")
                    .header("Authorization", "Bearer " + apiKey);
            if (jsonBody != null) {
                builder.header("Content-Type", "application/json");
                builder.method(method, HttpRequest.BodyPublishers.ofString(jsonBody));
            } else {
                builder.GET();
            }
            HttpResponse<String> response = http.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                // 临时诊断日志：只记录主机+路径+状态码与 Key 前缀指纹，不落完整密钥与响应体。
                log.warn("SCIVERSE outbound {} {} -> {} (key fingerprint={})",
                        method, uri, response.statusCode(),
                        apiKey.length() > 6 ? apiKey.substring(0, 6) + "…(" + apiKey.length() + " chars)" : "short/blank");
                throw new SciverseNotConfiguredException("SCIVERSE_HTTP_" + response.statusCode());
            }
            return mapper.readTree(response.body() == null || response.body().isBlank() ? "{}" : response.body());
        } catch (SciverseNotConfiguredException rethrown) {
            throw rethrown;
        } catch (Exception failure) {
            // 只落稳定错误码，不落原始异常消息（可能携带内网主机信息）。
            throw new SciverseNotConfiguredException("SCIVERSE_CALL_FAILED");
        }
    }

    /** 对文档站能力名做容错解析：items/results/data/evidence 任一数组都认。 */
    private List<Evidence> parseEvidence(JsonNode root) {
        List<Evidence> out = new ArrayList<>();
        JsonNode array = firstArray(root, "items", "results", "data", "evidence", "hits");
        if (array == null) return out;
        for (JsonNode node : array) {
            String docId = firstText(node, "doc_id", "docId", "document_id", "id");
            String title = firstText(node, "title", "paper_title", "name");
            String locator = firstText(node, "locator", "location", "section", "page", "position");
            String text = firstText(node, "text", "snippet", "excerpt", "content", "chunk");
            if (text == null || text.isBlank()) continue;
            out.add(new Evidence(docId == null ? "" : docId, title == null ? "SciVerse 文献证据" : title,
                    locator == null ? "" : locator, text));
        }
        return out;
    }

    private JsonNode firstArray(JsonNode root, String... keys) {
        for (String key : keys) {
            JsonNode node = root.get(key);
            if (node != null && node.isArray()) return node;
        }
        // 根节点本身就是数组的情况
        if (root.isArray()) return root;
        // 常见包裹层：result.payload / data.records
        Iterator<Map.Entry<String, JsonNode>> fields = root.fields();
        while (fields.hasNext()) {
            JsonNode value = fields.next().getValue();
            if (value.isArray() && value.size() > 0) return value;
            if (value.isObject()) {
                JsonNode nested = firstArray(value, keys);
                if (nested != null) return nested;
            }
        }
        return null;
    }

    private String firstText(JsonNode node, String... keys) {
        for (String key : keys) {
            JsonNode value = node.get(key);
            if (value != null && value.isTextual() && !value.asText().isBlank()) return value.asText();
            if (value != null && value.isNumber()) return value.asText();
        }
        return null;
    }

    private String firstText(JsonNode root) {
        JsonNode array = firstArray(root, "segments", "sections", "chunks", "content");
        if (array != null) {
            StringBuilder merged = new StringBuilder();
            for (JsonNode node : array) {
                String text = firstText(node, "text", "content", "snippet");
                if (text != null && !text.isBlank()) merged.append(text).append("\n\n");
            }
            if (merged.length() > 0) return merged.toString().trim();
        }
        return firstText(root, "content", "text", "fulltext");
    }

    private static String encode(String value) {
        return java.net.URLEncoder.encode(value == null ? "" : value, java.nio.charset.StandardCharsets.UTF_8);
    }
}
