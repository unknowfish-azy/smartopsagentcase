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
 * 知乎官方 API 检索（形态 B，id=ZHIHU_OFFICIAL）。
 *
 * <p>与百度官方形态相互独立：独立开关/凭证/endpoint/错误码/测试，互不为默认值、互不 fallback。
 * 期望响应为 {@code {"items":[{"title","url","snippet","publishedAt"}]}}；
 * 官方网关由 SMARTOPS_WR_ZHIHU_API_KEY / endpoint 显式指定。</p>
 */
@Component
public class ZhihuOfficialConnector implements ResearchConnector {

    private final KnowledgeCrawlService crawler;
    private final boolean enabled;
    private final String apiKey;
    private final String endpoint;
    private final ObjectMapper mapper = new ObjectMapper();

    public ZhihuOfficialConnector(KnowledgeCrawlService crawler,
                                  @Value("${smartops.web-research.connectors.zhihu-official.enabled:false}") boolean enabled,
                                  @Value("${smartops.web-research.connectors.zhihu-official.api-key:}") String apiKey,
                                  @Value("${smartops.web-research.connectors.zhihu-official.endpoint:}") String endpoint) {
        this.crawler = crawler;
        this.enabled = enabled;
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.endpoint = endpoint == null ? "" : endpoint.trim();
    }

    @Override
    public String id() {
        return "ZHIHU_OFFICIAL";
    }

    @Override
    public boolean isEnabled() {
        return enabled && !apiKey.isBlank() && !endpoint.isBlank();
    }

    @Override
    public List<WebResearchService.SearchResult> search(SessionUser actor, String query, int limit) throws IOException, InterruptedException {
        if (!isEnabled()) throw new BusinessException(409, "ZHIHU_OFFICIAL_NOT_CONFIGURED");
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
            results.add(WebResearchService.buildResult(url, title, "ZHIHU_OFFICIAL",
                    OperationRedactor.redact(item.path("snippet").asText("")),
                    item.path("publishedAt").isTextual() ? item.path("publishedAt").asText() : null));
        }
        if (results.isEmpty()) throw new BusinessException(502, "ZHIHU_OFFICIAL_FAILED");
        return results;
    }
}
