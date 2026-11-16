package com.smartops.knowledge.connector;

import com.smartops.exception.BusinessException;
import com.smartops.knowledge.WebRenderService;
import com.smartops.knowledge.WebResearchService;
import com.smartops.security.SessionUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.util.List;
import java.util.Locale;

/**
 * 指定 URL 读取扩展 · 百度域（形态 C，id=BAIDU_URL）。
 *
 * <p>只读取用户自带链接中属于百度域的公开页面（走 T33 受控渲染），不新增通用爬虫、
 * 不访问用户未提供的 URL。独立开关，默认关闭；不参与检索聚合。</p>
 */
@Component
public class BaiduUrlConnector implements ResearchConnector {

    private final WebRenderService renderService;
    private final boolean enabled;

    public BaiduUrlConnector(WebRenderService renderService,
                             @Value("${smartops.web-research.connectors.baidu-url.enabled:false}") boolean enabled) {
        this.renderService = renderService;
        this.enabled = enabled;
    }

    @Override
    public String id() {
        return "BAIDU_URL";
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public boolean supportsSearch() {
        return false;
    }

    @Override
    public List<WebResearchService.SearchResult> search(SessionUser actor, String query, int limit) {
        throw new BusinessException(400, "CONNECTOR_SEARCH_UNSUPPORTED");
    }

    @Override
    public WebResearchService.WebPage fetch(SessionUser actor, String url) {
        if (!isBaiduUrl(url)) throw new BusinessException(400, "BAIDU_URL_REJECTED");
        try {
            return renderService.fetchRendered(actor, url);
        } catch (BusinessException failure) {
            throw new BusinessException(failure.getCode(), failure.getMessage().contains("RENDER")
                    || failure.getMessage().contains("EMPTY_CONTENT")
                    ? "BAIDU_URL_UNREADABLE" : failure.getMessage());
        }
    }

    static boolean isBaiduUrl(String url) {
        try {
            String host = URI.create(url).getHost();
            if (host == null) return false;
            host = host.toLowerCase(Locale.ROOT);
            return host.equals("baidu.com") || host.endsWith(".baidu.com");
        } catch (Exception invalid) {
            return false;
        }
    }
}
