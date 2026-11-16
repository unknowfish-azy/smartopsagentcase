package com.smartops.knowledge.connector;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.knowledge.KnowledgeCrawlService;
import com.smartops.knowledge.WebResearchService;
import com.smartops.operations.OperationRedactor;
import com.smartops.security.SessionUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 百度官方 API 检索（形态 B，id=BAIDU_OFFICIAL）。
 *
 * <p>仅在凭证与授权齐备时启用：enabled + api-key + endpoint 三者齐备才 isEnabled()，
 * 任一缺失即跳过（configured=false），不回退到公开页形态，不伪造可用。
 * 出网走共享安全链（带 Authorization 头的重载），不自建 HTTP 客户端。
 * 期望响应为 {@code {"items":[{"title","url","snippet","publishedAt"}]}}；
 * 官方网关由 SMARTOPS_WR_BAIDU_API_KEY / endpoint 显式指定。</p>
 */
@Component
public class BaiduOfficialConnector implements ResearchConnector {

    private final KnowledgeCrawlService crawler;
    private final boolean enabled;
    private final String apiKey;
    private final String endpoint;
    private final ObjectMapper mapper = new ObjectMapper();

    public BaiduOfficialConnector(KnowledgeCrawlService crawler,
                                  @Value("${smartops.web-research.connectors.baidu-official.enabled:false}") boolean enabled,
                                  @Value("${smartops.web-research.connectors.baidu-official.api-key:}") String apiKey,
                                  @Value("${smartops.web-research.connectors.baidu-official.endpoint:}") String endpoint) {
        this.crawler = crawler;
        this.enabled = enabled;
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.endpoint = endpoint == null ? "" : endpoint.trim();
    }

    @Override
    public String id() {
        return "BAIDU_OFFICIAL";
    }

    @Override
    public boolean isEnabled() {
        return enabled && !apiKey.isBlank() && !endpoint.isBlank();
    }

    @Override
    public List<WebResearchService.SearchResult> search(SessionUser actor, String query, int limit) throws IOException, InterruptedException {
        if (!isEnabled()) throw new BusinessException(409, "BAIDU_OFFICIAL_NOT_CONFIGURED");
        String url = endpoint + (endpoint.contains("?") ? "&" : "?")
                + "query=" + URLEncoder.encode(query, StandardCharsets.UTF_8) + "&limit=" + limit;
        String json = crawler.fetch(url, "application/json", Map.of("Authorization", "Bearer " + apiKey));
        return parse(json, limit);
    }

    private List<WebResearchService.SearchResult> parse(String json, int limit) throws IOException {
        JsonNode root = mapper.readTree(json);
        List<WebResearchService.SearchResult> results = new ArrayList<>();
        for (JsonNode item : root.path("items")) {
            if (results.size() >= limit) break;
            String url = item.path("url").asText("");
            String title = item.path("title").asText("");
            if (url.isBlank() || title.isBlank()) continue;
            results.add(WebResearchService.buildResult(url, title, "BAIDU_OFFICIAL",
                    OperationRedactor.redact(item.path("snippet").asText("")),
                    item.path("publishedAt").isTextual() ? item.path("publishedAt").asText() : null));
        }
        if (results.isEmpty()) throw new BusinessException(502, "BAIDU_OFFICIAL_FAILED");
        return results;
    }
}
