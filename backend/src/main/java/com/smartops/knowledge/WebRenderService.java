package com.smartops.knowledge;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRedactor;
import com.smartops.security.OutboundUrlPolicy;
import com.smartops.security.SessionUser;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.time.Instant;

/**
 * JS 渲染只读工具（T33）：静态抓取之外的按页显式渲染通道。
 *
 * <p>静态分支直接复用 {@link WebResearchService#fetch}（等价既有链路）；JS 分支走受控渲染器，
 * 出站前统一 {@link OutboundUrlPolicy} 校验（不新造白名单），提取文本一律脱敏，
 * 任务/快照复用 web_research_task / web_research_page 既有表。渲染不可用或失败时落明确错误码，
 * 绝不回退伪造静态正文。</p>
 */
@Service
public class WebRenderService {

    private final WebResearchService research;
    private final HeadlessRenderer renderer;
    private final WebRenderSessionService sessions;

    public WebRenderService(WebResearchService research, HeadlessRenderer renderer, WebRenderSessionService sessions) {
        this.research = research;
        this.renderer = renderer;
        this.sessions = sessions;
    }

    /**
     * @param useJs false = 静态链路（等价 fetch）；true = 受控 JS 渲染（按页显式选择）
     */
    public WebResearchService.WebPage fetchRendered(SessionUser actor, String value, boolean useJs) {
        if (actor == null) throw new BusinessException(401, "登录状态已失效");
        if (value == null || value.isBlank()) throw new BusinessException(400, "WEB_RENDER_URL_REQUIRED");
        String url;
        try {
            url = KnowledgeCrawlService.normalizeUrl(value);
            if (!OutboundUrlPolicy.inspect(URI.create(url)).allowed()) {
                throw new BusinessException(400, "WEB_RENDER_URL_BLOCKED");
            }
        } catch (OutboundUrlPolicy.BlockedUrlException blocked) {
            // 策略层阻断（内网/保留网段等）归一为本工具错误码：仍是同一策略，不新造白名单
            throw new BusinessException(400, "WEB_RENDER_URL_BLOCKED");
        } catch (BusinessException blocked) {
            throw "KNOWLEDGE_CRAWL_URL_BLOCKED".equals(blocked.getMessage())
                    ? new BusinessException(400, "WEB_RENDER_URL_BLOCKED") : blocked;
        }
        if (!useJs) return research.fetch(actor, url);
        return fetchWithJs(actor, url);
    }

    private WebResearchService.WebPage fetchWithJs(SessionUser actor, String url) {
        if (!renderer.isAvailable()) throw new BusinessException(503, "RENDERER_UNAVAILABLE");
        long taskId = research.createTask(actor.id(), "FETCH_JS", KnowledgeCrawlService.stripQuery(url));
        try {
            String storageState = sessions.storageStateForRender(actor);
            HeadlessRenderer.RenderedPage rendered = renderer.render(url, storageState);
            String text = OperationRedactor.redact(trim(rendered.text(), 16_000));
            if (text.isBlank()) throw new BusinessException(422, "WEB_RESEARCH_EMPTY_CONTENT");
            String title = OperationRedactor.redact(trim(rendered.title(), 200));
            String hash = KnowledgeCrawlService.sha256(text);
            Instant fetchedAt = Instant.now();
            String displayUrl = KnowledgeCrawlService.stripQuery(url);
            research.savePageSnapshot(taskId, actor.id(), displayUrl, title, trim(text, 600), text, hash, fetchedAt);
            String note = storageState == null
                    ? "JS 渲染 · 匿名会话"
                    : "JS 渲染 · 使用本人登录接续";
            research.finishTask(taskId, "SUCCESS", 1, null);
            return new WebResearchService.WebPage(taskId, url, displayUrl, host(url), title,
                    trim(text, 600), text, hash, fetchedAt, "JS", note);
        } catch (BusinessException failure) {
            research.finishTask(taskId, "FAILED", 0, failure.getMessage());
            throw failure;
        } catch (Exception failure) {
            research.finishTask(taskId, "FAILED", 0, "RENDER_FAILED");
            throw new BusinessException(502, "WEB_RESEARCH_RENDER_FAILED");
        }
    }

    private static String host(String url) {
        try {
            String host = URI.create(url).getHost();
            return host == null ? "unknown" : host.toLowerCase(java.util.Locale.ROOT);
        } catch (Exception invalid) {
            return "unknown";
        }
    }

    private static String trim(String value, int limit) {
        return value == null ? "" : value.length() > limit ? value.substring(0, limit) : value;
    }
}
