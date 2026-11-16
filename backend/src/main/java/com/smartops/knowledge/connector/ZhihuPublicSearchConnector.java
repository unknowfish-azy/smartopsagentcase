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
 * 知乎公开页面只读检索（形态 A，id=ZHIHU_PUBLIC）。
 *
 * <p>知乎公开搜索页通常要求登录；遇登录墙/风控页如实返回 ZHIHU_CHALLENGE_REQUIRED，
 * 不破解不代填。独立开关，默认关闭。</p>
 */
@Component
public class ZhihuPublicSearchConnector implements ResearchConnector {

    private static final Pattern RESULT_ANCHOR = Pattern.compile(
            "<a[^>]+href=\"(/question/\\d+[^\"]*|/p/\\d+[^\"]*|https://zhuanlan\\.zhihu\\.com/p/\\d+[^\"]*)\"[^>]*>(.*?)</a>",
            Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern EXCERPT = Pattern.compile(
            "<span[^>]*class=\"[^\"]*Highlight[^\"]*\"[^>]*>(.*?)</span>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);

    private final KnowledgeCrawlService crawler;
    private final boolean enabled;

    public ZhihuPublicSearchConnector(KnowledgeCrawlService crawler,
                                      @Value("${smartops.web-research.connectors.zhihu-public.enabled:false}") boolean enabled) {
        this.crawler = crawler;
        this.enabled = enabled;
    }

    @Override
    public String id() {
        return "ZHIHU_PUBLIC";
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public List<WebResearchService.SearchResult> search(SessionUser actor, String query, int limit) throws IOException, InterruptedException {
        String endpoint = "https://www.zhihu.com/search?type=content&q=" + URLEncoder.encode(query, StandardCharsets.UTF_8);
        String html = crawler.fetch(endpoint, "text/html,application/xhtml+xml");
        String text = KnowledgeCrawlService.htmlToText(html);
        if (text.contains("系统监测到您的网络环境存在异常") || text.contains("登录查看")
                || html.contains("/signin") || html.contains(".accounts.zhihu.com")) {
            throw new BusinessException(403, "ZHIHU_CHALLENGE_REQUIRED");
        }
        List<WebResearchService.SearchResult> results = new ArrayList<>();
        Map<String, String> excerpts = excerptByOrder(html);
        Matcher anchor = RESULT_ANCHOR.matcher(html);
        while (anchor.find() && results.size() < limit) {
            String href = anchor.group(1);
            String url = href.startsWith("http") ? href : "https://www.zhihu.com" + href;
            String title = KnowledgeCrawlService.htmlToText(anchor.group(2));
            if (title.isBlank()) continue;
            results.add(WebResearchService.buildResult(url, title, "ZHIHU_PUBLIC",
                    excerpts.getOrDefault(String.valueOf(results.size()), ""), null));
        }
        if (results.isEmpty()) throw new BusinessException(502, "ZHIHU_PUBLIC_FAILED");
        return results;
    }

    private static Map<String, String> excerptByOrder(String html) {
        Map<String, String> excerpts = new LinkedHashMap<>();
        Matcher matcher = EXCERPT.matcher(html);
        int index = 0;
        while (matcher.find()) {
            excerpts.put(String.valueOf(index++), KnowledgeCrawlService.htmlToText(matcher.group(1)));
        }
        return excerpts;
    }
}
