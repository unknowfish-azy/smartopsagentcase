package com.smartops.knowledge;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRedactor;
import com.smartops.security.OutboundUrlPolicy;
import com.smartops.security.SessionUser;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Locale;

/**
 * JS 渲染只读工具（T33）：静态抓取之外的按页显式渲染通道。
 *
 * <p>只负责 JS 渲染路径（静态链路由 {@code /api/web-research/fetch} 承担）；出站前统一
 * {@link OutboundUrlPolicy} 校验（不新造白名单），提取文本一律脱敏，任务/快照写入
 * web_research_task / web_research_page 既有表（与静态链路共用数据语义）。
 * 渲染不可用或失败时落明确错误码，绝不回退伪造静态正文。
 * 注意：本服务不依赖 WebResearchService（避免 connectors→URL 连接器→本服务→检索服务 的循环）。</p>
 */
@Service
public class WebRenderService {

    private static final int MAX_PAGE_TEXT = 16_000;

    private final JdbcTemplate jdbc;
    private final HeadlessRenderer renderer;
    private final WebRenderSessionService sessions;

    public WebRenderService(JdbcTemplate jdbc, HeadlessRenderer renderer, WebRenderSessionService sessions) {
        this.jdbc = jdbc;
        this.renderer = renderer;
        this.sessions = sessions;
    }

    public WebResearchService.WebPage fetchRendered(SessionUser actor, String value) {
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
        if (!renderer.isAvailable()) throw new BusinessException(503, "RENDERER_UNAVAILABLE");
        long taskId = createTask(actor.id(), KnowledgeCrawlService.stripQuery(url));
        try {
            String storageState = sessions.storageStateForRender(actor);
            HeadlessRenderer.RenderedPage rendered = renderer.render(url, storageState);
            String text = OperationRedactor.redact(trim(rendered.text(), MAX_PAGE_TEXT));
            if (text.isBlank()) throw new BusinessException(422, "WEB_RESEARCH_EMPTY_CONTENT");
            String title = OperationRedactor.redact(trim(rendered.title(), 200));
            String hash = KnowledgeCrawlService.sha256(text);
            Instant fetchedAt = Instant.now();
            String displayUrl = KnowledgeCrawlService.stripQuery(url);
            savePageSnapshot(taskId, actor.id(), displayUrl, title, trim(text, 600), text, hash, fetchedAt);
            String note = storageState == null ? "JS 渲染 · 匿名会话" : "JS 渲染 · 使用本人登录接续";
            finishTask(taskId, "SUCCESS", 1, null);
            return new WebResearchService.WebPage(taskId, url, displayUrl, host(url), title,
                    trim(text, 600), text, hash, fetchedAt, "JS", note);
        } catch (BusinessException failure) {
            finishTask(taskId, "FAILED", 0, failure.getMessage());
            throw failure;
        } catch (Exception failure) {
            finishTask(taskId, "FAILED", 0, "RENDER_FAILED");
            throw new BusinessException(502, "WEB_RESEARCH_RENDER_FAILED");
        }
    }

    // 与 WebResearchService 同表同语义的任务/快照写入（独立实现以斩断 bean 循环依赖）
    private long createTask(long userId, String query) {
        GeneratedKeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement(
                    "INSERT INTO web_research_task(user_id,task_type,query_text,status,result_count,created_at) VALUES(?,?,'',?,0,?)",
                    new String[]{"id"});
            statement.setLong(1, userId);
            statement.setString(2, "FETCH_JS");
            statement.setString(3, "RUNNING");
            statement.setTimestamp(4, Timestamp.from(Instant.now()));
            return statement;
        }, keys);
        return keys.getKey().longValue();
    }

    private void finishTask(long taskId, String status, int count, String error) {
        jdbc.update("UPDATE web_research_task SET status=?,result_count=?,error_code=?,finished_at=? WHERE id=?",
                status, count, error, Timestamp.from(Instant.now()), taskId);
    }

    private void savePageSnapshot(long taskId, long userId, String url, String title, String excerpt,
                                  String content, String hash, Instant fetchedAt) {
        jdbc.update("INSERT INTO web_research_page(task_id,user_id,url,title,excerpt,content,content_hash,fetched_at) VALUES(?,?,?,?,?,?,?,?)",
                taskId, userId, url, title, excerpt, content, hash, Timestamp.from(fetchedAt));
    }

    private static String host(String url) {
        try {
            String host = URI.create(url).getHost();
            return host == null ? "unknown" : host.toLowerCase(Locale.ROOT);
        } catch (Exception invalid) {
            return "unknown";
        }
    }

    private static String trim(String value, int limit) {
        return value == null ? "" : value.length() > limit ? value.substring(0, limit) : value;
    }
}
