package com.smartops.knowledge.connector;

import com.smartops.exception.BusinessException;
import com.smartops.knowledge.KnowledgeCrawlService;
import com.smartops.knowledge.WebResearchService;
import com.smartops.security.SessionUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 百度公开页面只读检索（形态 A，id=BAIDU_PUBLIC）。
 *
 * <p>只抓公开搜索结果页并做只读解析；遇登录墙/验证码/风控页如实返回 BAIDU_CHALLENGE_REQUIRED，
 * 绝不破解、代填或伪装指纹。独立开关，默认关闭。</p>
 */
@Component
public class BaiduPublicSearchConnector implements ResearchConnector {

    private static final Pattern RESULT_ANCHOR = Pattern.compile(
            "<h3[^>]*>\\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern ABSTRACT = Pattern.compile(
            "<div[^>]*class=\"[^\"]*c-abstract[^\"]*\"[^>]*>(.*?)</div>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);

    private final KnowledgeCrawlService crawler;
    private final boolean enabled;

    public BaiduPublicSearchConnector(KnowledgeCrawlService crawler,
                                      @Value("${smartops.web-research.connectors.baidu-public.enabled:false}") boolean enabled) {
        this.crawler = crawler;
        this.enabled = enabled;
    }

    @Override
    public String id() {
        return "BAIDU_PUBLIC";
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public List<WebResearchService.SearchResult> search(SessionUser actor, String query, int limit) throws IOException, InterruptedException {
        String endpoint = "https://www.baidu.com/s?wd=" + URLEncoder.encode(query, StandardCharsets.UTF_8)
                + "&rn=" + Math.min(limit, 10);
        String html = crawler.fetch(endpoint, "text/html,application/xhtml+xml");
        String text = KnowledgeCrawlService.htmlToText(html);
        if (text.contains("百度安全验证") || html.contains("wappass.baidu.com")) {
            throw new BusinessException(403, "BAIDU_CHALLENGE_REQUIRED");
        }
        List<WebResearchService.SearchResult> results = new ArrayList<>();
        Map<String, String> snippets = abstractByOrder(html);
        Matcher anchor = RESULT_ANCHOR.matcher(html);
        while (anchor.find() && results.size() < limit) {
            String title = KnowledgeCrawlService.htmlToText(anchor.group(2));
            if (title.isBlank()) continue;
            results.add(WebResearchService.buildResult(anchor.group(1), title, "BAIDU_PUBLIC",
                    snippets.getOrDefault(String.valueOf(results.size()), ""), null));
        }
        if (results.isEmpty()) throw new BusinessException(502, "BAIDU_PUBLIC_FAILED");
        return results;
    }

    /** c-abstract 摘要按出现顺序对应结果顺序（尽力而为，缺失即为空串）。 */
    private static Map<String, String> abstractByOrder(String html) {
        Map<String, String> snippets = new LinkedHashMap<>();
        Matcher matcher = ABSTRACT.matcher(html);
        int index = 0;
        while (matcher.find()) {
            snippets.put(String.valueOf(index++), KnowledgeCrawlService.htmlToText(matcher.group(1)));
        }
        return snippets;
    }
}
