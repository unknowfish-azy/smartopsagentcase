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

/** GitHub 官方 API 检索（原 GITHUB 形态迁移，行为不变）。 */
@Component
public class GithubConnector implements ResearchConnector {

    private final KnowledgeCrawlService crawler;
    private final boolean enabled;

    public GithubConnector(KnowledgeCrawlService crawler,
                           @Value("${smartops.web-research.connectors.github.enabled:false}") boolean enabled) {
        this.crawler = crawler;
        this.enabled = enabled;
    }

    @Override
    public String id() {
        return "GITHUB";
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public List<WebResearchService.SearchResult> search(SessionUser actor, String query, int limit) throws IOException, InterruptedException {
        String endpoint = "https://api.github.com/search/repositories?q="
                + URLEncoder.encode(query, StandardCharsets.UTF_8) + "&per_page=" + limit;
        String json = crawler.fetch(endpoint, "application/vnd.github+json,application/json");
        return WebResearchService.parseGithubResults(json, limit);
    }
}
