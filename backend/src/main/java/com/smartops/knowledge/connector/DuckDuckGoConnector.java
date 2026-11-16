package com.smartops.knowledge.connector;

import com.smartops.knowledge.KnowledgeCrawlService;
import com.smartops.knowledge.WebResearchService;
import com.smartops.security.SessionUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;

/** DuckDuckGo HTML 公开检索（原 WEB 形态迁移，行为不变）。 */
@Component
public class DuckDuckGoConnector implements ResearchConnector {

    private final KnowledgeCrawlService crawler;
    private final boolean enabled;

    public DuckDuckGoConnector(KnowledgeCrawlService crawler,
                               @Value("${smartops.web-research.connectors.ddg.enabled:false}") boolean enabled) {
        this.crawler = crawler;
        this.enabled = enabled;
    }

    @Override
    public String id() {
        return "DDG";
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public List<WebResearchService.SearchResult> search(SessionUser actor, String query, int limit) throws IOException, InterruptedException {
        String endpoint = "https://html.duckduckgo.com/html/?q=" + URLEncoder.encode(query, StandardCharsets.UTF_8);
        String html = crawler.fetch(endpoint, "text/html,application/xhtml+xml");
        // 解析逻辑迁移自旧 WEB 分支（行为等价）；kind 按形态标识重标，不再笼统标 WEB
        return WebResearchService.parseWebResults(html, limit).stream()
                .map(result -> WebResearchService.buildResult(result.url(), result.title(), "DDG",
                        result.snippet(), result.publishedAt()))
                .toList();
    }
}
