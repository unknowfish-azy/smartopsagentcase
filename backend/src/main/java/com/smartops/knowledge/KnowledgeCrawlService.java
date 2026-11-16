package com.smartops.knowledge;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRedactor;
import com.smartops.security.OutboundUrlPolicy;
import com.smartops.security.PinnedDns;
import com.smartops.security.SessionUser;
import com.smartops.service.KnowledgeCandidateService;
import com.smartops.service.PersonalKnowledgeService;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.classic.methods.HttpGet;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.CloseableHttpResponse;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 知识库网页采集：把同域静态站点的新增/变更页面抓成待审知识候选。
 * 正式知识条目只能由审核人员在候选中心采纳，采集与雷达不直接写入。
 *
 * <p>抓取过程是同步的，网络请求不包事务；每页独立落库，单页失败不影响整轮。</p>
 */
@Service
public class KnowledgeCrawlService {
    private static final String USER_AGENT = "SmartOpsAgent-KnowledgeCrawler/1.0";
    private static final int MAX_CONTENT = 20_000;
    // SEC-06：下载侧上限。MAX_CONTENT 只截断入库，不能阻止超大响应打满内存。
    private static final long MAX_DOWNLOAD_BYTES = 10L * 1024 * 1024;
    // 单次 run 的总时长预算：50 页 × 多跳的 8s 单跳超时会长期占用线程。
    private static final long RUN_DEADLINE_SECONDS = 60;
    // SEC-06 TM-25：全局并发爬取上限，避免多用户同时爬取耗尽 HTTP 连接池与线程。
    private static final int MAX_CONCURRENT_CRAWLS = 4;
    private static final Semaphore CRAWL_PERMITS = new Semaphore(MAX_CONCURRENT_CRAWLS, true);
    private static final long PERMIT_ACQUIRE_TIMEOUT_SECONDS = 5;
    // personal_knowledge_entry.source_ref 只有 255，超长 URL 会插不进去，也无法按 URL 稳定比对
    private static final int MAX_URL = 255;
    private static final Pattern LINK = Pattern.compile("<a\\b[^>]*?\\bhref\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+))", Pattern.CASE_INSENSITIVE);
    private static final Pattern TITLE = Pattern.compile("<title[^>]*>(.*?)</title>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern SCRIPT = Pattern.compile("<script\\b[^>]*>.*?</script>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern STYLE = Pattern.compile("<style\\b[^>]*>.*?</style>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern COMMENT = Pattern.compile("<!--.*?-->", Pattern.DOTALL);
    private static final Pattern BLOCK = Pattern.compile("</?(?:p|div|br|hr|li|ul|ol|tr|td|th|table|thead|tbody|section|article|header|footer|nav|aside|main|h[1-6]|blockquote|pre|form|figure|figcaption)\\b[^>]*>", Pattern.CASE_INSENSITIVE);
    private static final Pattern TAG = Pattern.compile("<[^>]+>");
    private static final Pattern ASSET = Pattern.compile(".*\\.(?:css|js|mjs|png|jpe?g|gif|svg|ico|webp|pdf|zip|gz|tar|mp4|mp3|woff2?|ttf)(?:\\?.*)?$", Pattern.CASE_INSENSITIVE);
    private static final String SOURCE_COLUMNS = "id,library_id,name,seed_url,max_pages,depth,last_run_at,last_status,last_error,monitor_enabled,monitor_interval_minutes,next_run_at,created_at";

    private final JdbcTemplate jdbc;
    private final PersonalKnowledgeService knowledge;
    private final KnowledgeCandidateService candidates;
    private final WebResearchMetrics metrics;
    // T41：JS 渲染降级。SPA 页面静态抓取只有骨架（正文为空），走受控无头渲染补齐；
    // 渲染不可用/失败时如实回退静态结果，绝不伪造正文。
    private final HeadlessRenderer renderer;

    @org.springframework.beans.factory.annotation.Value("${smartops.knowledge.radar.claim-lease-ms:120000}")
    private long claimLeaseMs = 120_000;
    // SEC-06 连接期 DNS pin：java.net.http 在 JDK 17 上没有解析钩子，改用
    // Apache HttpClient 5 + fail-closed 的 PinnedDns 解析器——建连只能拿到
    // OutboundUrlPolicy 校验过的地址，DNS rebinding 窗口关闭。
    // 重定向仍由 fetch() 手动逐跳处理（disableRedirectHandling），每跳重新校验并重新 pin。
    private final CloseableHttpClient client;

    public KnowledgeCrawlService(JdbcTemplate jdbc, PersonalKnowledgeService knowledge) {
        this(jdbc, knowledge, new KnowledgeCandidateService(jdbc, null, knowledge));
    }

    public KnowledgeCrawlService(JdbcTemplate jdbc, PersonalKnowledgeService knowledge, KnowledgeCandidateService candidates) {
        this(jdbc, knowledge, candidates, null, null);
    }

    @org.springframework.beans.factory.annotation.Autowired
    public KnowledgeCrawlService(JdbcTemplate jdbc, PersonalKnowledgeService knowledge, KnowledgeCandidateService candidates,
                                 WebResearchMetrics metrics, HeadlessRenderer renderer) {
        this.jdbc = jdbc;
        this.knowledge = knowledge;
        this.candidates = candidates;
        this.metrics = metrics;
        this.renderer = renderer;
        PoolingHttpClientConnectionManager connections = PoolingHttpClientConnectionManagerBuilder.create()
                .setDnsResolver(new org.apache.hc.client5.http.DnsResolver() {
                    @Override
                    public java.net.InetAddress[] resolve(String host) throws java.net.UnknownHostException {
                        return PinnedDns.resolve(host);
                    }

                    @Override
                    public String resolveCanonicalHostname(String host) throws java.net.UnknownHostException {
                        // 只允许已 pin 的主机；规范名即原始主机名，不做额外解析。
                        PinnedDns.resolve(host);
                        return host;
                    }
                })
                .setDefaultConnectionConfig(ConnectionConfig.custom()
                        .setConnectTimeout(Timeout.ofSeconds(8))
                        .build())
                .setMaxConnTotal(4)
                .setMaxConnPerRoute(4)
                .build();
        this.client = HttpClients.custom()
                .setConnectionManager(connections)
                .disableRedirectHandling()
                .disableAutomaticRetries()
                .setDefaultRequestConfig(RequestConfig.custom()
                        .setConnectionRequestTimeout(Timeout.ofSeconds(8))
                        .setResponseTimeout(Timeout.ofSeconds(8))
                        .build())
                .setUserAgent(USER_AGENT)
                .build();
    }

    public CrawlSource createSource(SessionUser actor, Long libraryId, String name, String seedUrl, Integer maxPages, Integer depth) {
        requireActor(actor);
        if (libraryId == null) throw new BusinessException(400, "KNOWLEDGE_CRAWL_LIBRARY_REQUIRED");
        knowledge.detailLibrary(actor.id(), libraryId);
        if (name == null || name.isBlank()) throw new BusinessException(400, "KNOWLEDGE_CRAWL_NAME_REQUIRED");
        String url = normalizeUrl(seedUrl);
        int pages = clamp(maxPages, 1, 50, 20);
        int level = clamp(depth, 0, 2, 1);
        // SEC-09：直接取本次插入主键，避免同用户并发创建时 MAX(id) 取到他人的 source。
        var keys = new org.springframework.jdbc.support.GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("INSERT INTO knowledge_crawl_source(user_id,library_id,name,seed_url,max_pages,depth,created_at) VALUES(?,?,?,?,?,?,?)", new String[]{"id"});
            statement.setObject(1, actor.id());
            statement.setObject(2, libraryId);
            statement.setObject(3, trimTo(name.trim(), 120));
            statement.setObject(4, url);
            statement.setObject(5, pages);
            statement.setObject(6, level);
            statement.setObject(7, Timestamp.from(Instant.now()));
            return statement;
        }, keys);
        return detailSource(actor.id(), keys.getKey().longValue());
    }

    public List<CrawlSource> listSources(SessionUser actor) {
        requireActor(actor);
        return jdbc.query("SELECT " + SOURCE_COLUMNS + " FROM knowledge_crawl_source WHERE user_id=? ORDER BY id DESC", this::mapSource, actor.id());
    }

    /** 开启或暂停某个来源的自动时效检测。检测周期只影响该来源，不修改采集范围。 */
    public CrawlSource updateMonitor(SessionUser actor, long sourceId, boolean enabled, Integer intervalMinutes) {
        requireActor(actor);
        detailSource(actor.id(), sourceId);
        int interval = clamp(intervalMinutes, 15, 10_080, 60);
        Timestamp nextRun = enabled ? Timestamp.from(Instant.now()) : null;
        jdbc.update("UPDATE knowledge_crawl_source SET monitor_enabled=?,monitor_interval_minutes=?,next_run_at=? WHERE id=? AND user_id=?",
                enabled, interval, nextRun, sourceId, actor.id());
        return detailSource(actor.id(), sourceId);
    }

    public List<CrawlPage> listPages(SessionUser actor, long sourceId, int limit) {
        requireActor(actor);
        detailSource(actor.id(), sourceId);
        int size = Math.max(1, Math.min(100, limit));
        return jdbc.query("SELECT id,url,title,content_hash,entry_id,change_type,fetched_at FROM knowledge_crawl_page WHERE source_id=? AND user_id=? ORDER BY id DESC LIMIT ?",
                (rs, row) -> new CrawlPage(rs.getLong("id"), rs.getString("url"), rs.getString("title"), rs.getString("content_hash"),
                        (Long) rs.getObject("entry_id"), rs.getString("change_type"), instant(rs.getTimestamp("fetched_at"))),
                sourceId, actor.id(), size);
    }

    public CrawlResult run(SessionUser actor, long sourceId) {
        requireActor(actor);
        // SEC-06 TM-25：全局并发爬取上限，超出即 429，避免耗尽连接池与线程。
        boolean acquired;
        try {
            acquired = CRAWL_PERMITS.tryAcquire(PERMIT_ACQUIRE_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new BusinessException(429, "KNOWLEDGE_CRAWL_BUSY");
        }
        if (!acquired) throw new BusinessException(429, "KNOWLEDGE_CRAWL_BUSY");
        try {
            return doRun(actor, sourceId);
        } finally {
            CRAWL_PERMITS.release();
        }
    }

    private CrawlResult doRun(SessionUser actor, long sourceId) {
        CrawlSource source = detailSource(actor.id(), sourceId);
        URI seed = URI.create(source.seedUrl());
        if (!OutboundUrlPolicy.inspect(seed).allowed()) {
            throw new BusinessException(400, "KNOWLEDGE_CRAWL_URL_BLOCKED");
        }
        String seedHost = seed.getHost();
        Deque<Link> queue = new ArrayDeque<>();
        Set<String> visited = new LinkedHashSet<>();
        queue.add(new Link(source.seedUrl(), 0));
        visited.add(source.seedUrl());
        int added = 0, updated = 0, unchanged = 0, failed = 0, pages = 0;
        List<String> errors = new ArrayList<>();
        Instant deadline = Instant.now().plusSeconds(RUN_DEADLINE_SECONDS);
        while (!queue.isEmpty() && pages < source.maxPages()) {
            if (Instant.now().isAfter(deadline)) {
                errors.add("抓取超出总时长预算（" + RUN_DEADLINE_SECONDS + " 秒）");
                break;
            }
            Link link = queue.poll();
            pages++;
            try {
                String html = fetch(link.url());
                String text = trimTo(htmlToText(html), MAX_CONTENT);
                String title = pageTitle(html, link.url());
                FallbackPage fallback = tryJsRenderFallback(link.url(), text, title);
                text = fallback.text();
                title = fallback.title();
                if (text.isBlank()) throw new IOException("页面没有可提取的正文");
                // SEC-11：正文与标题入库前脱敏，避免把页面里的凭据写成知识库内容。
                text = OperationRedactor.redact(text);
                String hash = sha256(text);
                title = OperationRedactor.redact(trimTo(title, 200));
                switch (persist(actor, source, link.url(), title, text, hash)) {
                    case "ADDED" -> added++;
                    case "UPDATED" -> updated++;
                    default -> unchanged++;
                }
                if (link.depth() < source.depth() && visited.size() < source.maxPages() * 5) {
                    for (String next : extractLinks(html, URI.create(link.url()), seedHost)) {
                        if (visited.add(next)) queue.add(new Link(next, link.depth() + 1));
                    }
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                errors.add(stripQuery(link.url()) + " 抓取被中断");
                break;
            } catch (Exception failure) {
                failed++;
                // SEC-11：只落我们生成的错误码，不落原始异常消息（可能带内部主机/端口）。
                errors.add(stripQuery(link.url()) + " " + errorCode(failure));
            }
            if (!queue.isEmpty() && pages < source.maxPages()) {
                try {
                    Thread.sleep(300);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }
        String status = failed == 0 ? "SUCCESS" : "PARTIAL";
        Instant checkedAt = Instant.now();
        Timestamp nextRun = source.monitorEnabled()
                ? Timestamp.from(checkedAt.plusSeconds(source.monitorIntervalMinutes() * 60L)) : null;
        jdbc.update("UPDATE knowledge_crawl_source SET last_run_at=?,last_status=?,last_error=?,next_run_at=? WHERE id=? AND user_id=?",
                Timestamp.from(checkedAt), status, trimTo(String.join("；", errors), 500), nextRun, sourceId, actor.id());
        return new CrawlResult(added, updated, unchanged, failed, pages);
    }

    /**
     * 每轮最多检测一个到期来源。来源内仍按既有串行预算执行，避免自动雷达挤占全部调度线程。
     */
    @org.springframework.scheduling.annotation.Scheduled(
            fixedDelayString = "${smartops.knowledge.radar.sweep-ms:30000}",
            initialDelayString = "${smartops.knowledge.radar.initial-delay-ms:60000}")
    public void runDueMonitor() {
        DueSource candidate = findDueSource();
        if (candidate == null) return;
        if (metrics != null) metrics.radarDue();
        ClaimedSource claimed = tryClaim(candidate);
        if (claimed == null) {
            // 已被其他副本领取且租约未过期：本轮跳过，如实计数，不伪造成功
            if (metrics != null) metrics.radarSkipped();
            return;
        }
        DueSource source = claimed.source();
        SessionUser actor = new SessionUser(source.userId(), "scheduled-radar", "user");
        try {
            run(actor, source.id());
            if (metrics != null) metrics.radarProcessed();
        } catch (Exception failure) {
            if (metrics != null) metrics.radarProcessed();
            CrawlSource current = detailSource(actor.id(), source.id());
            Instant checkedAt = Instant.now();
            Timestamp nextRun = Timestamp.from(checkedAt.plusSeconds(current.monitorIntervalMinutes() * 60L));
            jdbc.update("UPDATE knowledge_crawl_source SET last_run_at=?,last_status='FAILED',last_error=?,next_run_at=? WHERE id=? AND user_id=?",
                    Timestamp.from(checkedAt), trimTo(errorCode(failure), 500), nextRun, source.id(), actor.id());
        } finally {
            // 释放 claim（无论成败）；next_run_at 已由 run()/失败分支推进
            jdbc.update("UPDATE knowledge_crawl_source SET claim_token=NULL, claim_expiry=NULL WHERE id=? AND claim_token=?",
                    source.id(), claimed.token());
        }
    }

    private DueSource findDueSource() {
        Instant now = Instant.now();
        List<DueSource> due = jdbc.query("SELECT id,user_id FROM knowledge_crawl_source WHERE monitor_enabled=TRUE AND (next_run_at IS NULL OR next_run_at<=?) ORDER BY next_run_at ASC LIMIT 1",
                (rs, row) -> new DueSource(rs.getLong("id"), rs.getLong("user_id")), Timestamp.from(now));
        return due.isEmpty() ? null : due.get(0);
    }

    /** 条件更新领取；已被其他副本持有且租约未过期时返回 null。 */
    private ClaimedSource tryClaim(DueSource candidate) {
        Instant now = Instant.now();
        String token = java.util.UUID.randomUUID().toString();
        Timestamp lease = Timestamp.from(now.plusMillis(claimLeaseMs));
        int claimed = jdbc.update("UPDATE knowledge_crawl_source SET claim_token=?, claim_expiry=? WHERE id=? "
                        + "AND monitor_enabled=TRUE AND (next_run_at IS NULL OR next_run_at<=?) "
                        + "AND (claim_token IS NULL OR claim_expiry IS NULL OR claim_expiry<=?)",
                token, lease, candidate.id(), Timestamp.from(now), Timestamp.from(now));
        return claimed == 1 ? new ClaimedSource(candidate, token) : null;
    }

    /** 测试与运维入口：找到即领取；无到期或竞争失败返回 null。 */
    ClaimedSource claimNextSource() {
        DueSource candidate = findDueSource();
        return candidate == null ? null : tryClaim(candidate);
    }

    record DueSource(long id, long userId) {}
    record ClaimedSource(DueSource source, String token) {}

    /**
     * T41：JS 渲染降级。SPA 页面静态抓取只能拿到骨架（正文极短甚至为空），
     * 此时若受控无头渲染器可用，则匿名渲染同一 URL 补齐正文与标题。
     *
     * <p>诚实性约束：只采用「渲染结果比静态结果更长」的正文（防止把弹窗/骨架
     * 文本覆盖掉有效的静态正文）；渲染不可用或失败时原样返回静态结果，
     * 由上层如实按空正文/失败处理，绝不伪造。渲染 URL 与静态抓取同一来源，
     * 已经过 OutboundUrlPolicy 校验，renderer 内部不再重复放行校验。</p>
     */
    FallbackPage tryJsRenderFallback(String url, String staticText, String staticTitle) {
        final int minUsefulText = 200;
        if (staticText != null && staticText.length() >= minUsefulText) return new FallbackPage(staticText, staticTitle);
        if (renderer == null || !renderer.isAvailable()) return new FallbackPage(staticText, staticTitle);
        try {
            HeadlessRenderer.RenderedPage rendered = renderer.render(url, null);
            String renderedText = rendered == null ? "" : trimTo(OperationRedactor.redact(rendered.text() == null ? "" : rendered.text()), MAX_CONTENT);
            if (metrics != null) metrics.radarJsFallback();
            if (renderedText.length() > (staticText == null ? 0 : staticText.length())) {
                String renderedTitle = rendered.title() == null || rendered.title().isBlank() ? staticTitle : rendered.title();
                return new FallbackPage(renderedText, renderedTitle);
            }
            return new FallbackPage(staticText, staticTitle);
        } catch (Exception renderFailure) {
            // 渲染失败如实回退静态结果：上层按空正文抛"页面没有可提取的正文"，不伪造。
            return new FallbackPage(staticText, staticTitle);
        }
    }

    /** 降级后的页面字段（title/text），供入库统一脱敏与截断。 */
    record FallbackPage(String text, String title) {}

    String persist(SessionUser actor, CrawlSource source, String url, String title, String text, String hash) {
        // SEC-11：URL 的 query 可能携带 token，只存去 query 的地址用于稳定比对。
        String storedUrl = stripQuery(url);
        Instant fetchedAt = Instant.now();
        String lastHash = jdbc.query("SELECT content_hash FROM knowledge_crawl_page WHERE source_id=? AND url=? ORDER BY id DESC LIMIT 1",
                (rs, row) -> rs.getString(1), source.id(), storedUrl).stream().findFirst().orElse(null);
        List<Long> existing = jdbc.query("SELECT id FROM personal_knowledge_entry WHERE user_id=? AND library_id=? AND source_ref=? LIMIT 1",
                (rs, row) -> rs.getLong(1), actor.id(), source.libraryId(), storedUrl);
        Long entryId = existing.isEmpty() ? null : existing.get(0);
        String change;
        if (lastHash != null && lastHash.equals(hash)) {
            change = "UNCHANGED";
        } else {
            // 雷达只生成服务端快照与待审候选，不自动新建或覆盖正式知识条目。
            long taskId = createRadarSnapshot(actor, source, storedUrl, title, text, hash, fetchedAt);
            candidates.createFromWebResearch(actor.id(), taskId);
            change = lastHash == null ? "ADDED" : "UPDATED";
        }
        jdbc.update("INSERT INTO knowledge_crawl_page(source_id,user_id,url,title,content_md,content_hash,entry_id,change_type,fetched_at) VALUES(?,?,?,?,?,?,?,?,?)",
                source.id(), actor.id(), storedUrl, title, text, hash, entryId, change, Timestamp.from(fetchedAt));
        return change;
    }

    private long createRadarSnapshot(SessionUser actor, CrawlSource source, String url, String title,
                                     String text, String hash, Instant fetchedAt) {
        var keys = new org.springframework.jdbc.support.GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement(
                    "INSERT INTO web_research_task(user_id,task_type,query_text,status,result_count,created_at,finished_at) VALUES(?,?,?,?,?,?,?)",
                    new String[]{"id"});
            statement.setLong(1, actor.id());
            statement.setString(2, "RADAR");
            statement.setString(3, trimTo("雷达来源 #" + source.id() + " · " + url, 255));
            statement.setString(4, "SUCCESS");
            statement.setInt(5, 1);
            statement.setTimestamp(6, Timestamp.from(fetchedAt));
            statement.setTimestamp(7, Timestamp.from(fetchedAt));
            return statement;
        }, keys);
        long taskId = keys.getKey().longValue();
        jdbc.update("INSERT INTO web_research_page(task_id,user_id,url,title,excerpt,content,content_hash,fetched_at) VALUES(?,?,?,?,?,?,?,?)",
                taskId, actor.id(), url, title, trimTo(text, 160), text, hash, Timestamp.from(fetchedAt));
        return taskId;
    }

    public String fetch(String url) throws IOException, InterruptedException {
        return fetch(url, "text/html,application/xhtml+xml");
    }

    /** 同一安全出站链路供联网检索复用；每跳都执行公网校验与 DNS pin。 */
    public String fetch(String url, String accept) throws IOException, InterruptedException {
        return fetch(url, accept, java.util.Map.of());
    }

    /** 带自定义头的同链变体（官方 API 适配用，如 Authorization）；仍然逐跳校验 + DNS pin + 限额，不得绕过。 */
    public String fetch(String url, String accept, java.util.Map<String, String> extraHeaders) throws IOException, InterruptedException {
        String current = url;
        for (int hop = 0; hop < 4; hop++) {
            URI uri;
            try {
                uri = URI.create(current);
            } catch (IllegalArgumentException invalid) {
                throw new IOException("地址无效");
            }
            // SEC-06：首跳与每一跳都在发起连接前重新校验，尾点域名、IPv4-mapped
            // IPv6 与解析后落在内网/保留网段的地址一律拒绝。
            OutboundUrlPolicy.Decision decision = OutboundUrlPolicy.inspect(uri);
            if (!decision.allowed()) {
                throw new IOException("目标地址不允许访问（" + decision.rule() + "）");
            }
            // 连接期 pin：把校验过的地址登记给 DnsResolver，建连只能用这批地址
            // （未登记的主机在该 resolver 上直接解析失败，fail-closed）。
            PinnedDns.pin(uri.getHost(), decision.addresses());
            HttpGet request = new HttpGet(uri);
            request.setHeader("User-Agent", USER_AGENT);
            request.setHeader("Accept", accept);
            if (extraHeaders != null) {
                extraHeaders.forEach(request::setHeader);
            }
            try (CloseableHttpResponse response = client.execute(request)) {
                int code = response.getCode();
                String location = headerValue(response, "Location");
                if (code >= 200 && code < 300) {
                    long declared = -1L;
                    String declaredHeader = headerValue(response, "Content-Length");
                    if (declaredHeader != null) {
                        try {
                            declared = Long.parseLong(declaredHeader.trim());
                        } catch (NumberFormatException ignored) {
                            // 异常的 Content-Length 交给流式读取上限兜底
                        }
                    }
                    if (declared > MAX_DOWNLOAD_BYTES) throw new IOException("响应体超过下载上限");
                    try (InputStream body = response.getEntity() != null
                            ? response.getEntity().getContent() : null) {
                        return readBounded(body);
                    }
                }
                // 重定向目标同样要过内网校验，避免借跳转绕过 host 白名单
                if (code >= 300 && code < 400 && location != null) {
                    URI target = uri.resolve(location);
                    requirePublic(target);
                    current = target.toString();
                    continue;
                }
                throw new IOException("HTTP " + code);
            } finally {
                PinnedDns.clear(uri.getHost());
            }
        }
        throw new IOException("重定向次数过多");
    }

    /** HC5 的头部读取可能抛 ProtocolException（畸形头），按无此头处理。 */
    private static String headerValue(CloseableHttpResponse response, String name) {
        try {
            var header = response.getHeader(name);
            return header == null ? null : header.getValue();
        } catch (org.apache.hc.core5.http.ProtocolException invalid) {
            return null;
        }
    }

    private static String readBounded(InputStream body) throws IOException {
        ByteArrayOutputStream collected = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int read;
        while ((read = body.read(buffer)) != -1) {
            if (collected.size() + (long) read > MAX_DOWNLOAD_BYTES) {
                throw new IOException("响应体超过下载上限");
            }
            collected.write(buffer, 0, read);
        }
        return collected.toString(StandardCharsets.UTF_8);
    }

    private static void requirePublic(URI uri) throws IOException {
        OutboundUrlPolicy.Decision decision = OutboundUrlPolicy.inspect(uri);
        if (!decision.allowed()) {
            throw new IOException("目标地址不允许访问（" + decision.rule() + "）");
        }
    }

    private static List<String> extractLinks(String html, URI base, String seedHost) {
        List<String> links = new ArrayList<>();
        Matcher matcher = LINK.matcher(html);
        while (matcher.find()) {
            String raw = matcher.group(1) != null ? matcher.group(1) : matcher.group(2) != null ? matcher.group(2) : matcher.group(3);
            if (raw == null) continue;
            String value = raw.trim();
            if (value.isEmpty() || value.startsWith("#")
                    || value.regionMatches(true, 0, "javascript:", 0, 11)
                    || value.regionMatches(true, 0, "mailto:", 0, 7)) continue;
            URI resolved;
            try {
                resolved = base.resolve(value.replace(" ", "%20"));
            } catch (IllegalArgumentException invalid) {
                continue;
            }
            if (!isHttpTarget(resolved) || seedHost == null || !seedHost.equalsIgnoreCase(resolved.getHost())) continue;
            String normalized = resolved.toString();
            int fragment = normalized.indexOf('#');
            if (fragment >= 0) normalized = normalized.substring(0, fragment);
            if (normalized.length() > MAX_URL || ASSET.matcher(normalized).matches()) continue;
            links.add(normalized);
        }
        return links;
    }

    public static String htmlToText(String html) {
        String body = COMMENT.matcher(html).replaceAll(" ");
        body = SCRIPT.matcher(body).replaceAll(" ");
        body = STYLE.matcher(body).replaceAll(" ");
        body = BLOCK.matcher(body).replaceAll("\n");
        body = TAG.matcher(body).replaceAll(" ");
        body = decodeEntities(body).replace('\u00A0', ' ');
        StringBuilder text = new StringBuilder();
        for (String line : body.split("\\r?\\n")) {
            String trimmed = line.replaceAll("[\\t\\x0B\\f\\r]+", " ").replaceAll(" {2,}", " ").trim();
            if (trimmed.isEmpty()) continue;
            if (text.length() > 0) text.append('\n');
            text.append(trimmed);
        }
        return text.toString().trim();
    }

    public static String pageTitle(String html, String url) {
        Matcher matcher = TITLE.matcher(html);
        if (matcher.find()) {
            String title = decodeEntities(TAG.matcher(matcher.group(1)).replaceAll(" ")).replaceAll("\\s+", " ").trim();
            if (!title.isEmpty()) return title;
        }
        URI uri = URI.create(url);
        String path = uri.getPath();
        if (path == null || path.isBlank() || path.equals("/")) return uri.getHost();
        String segment = path.substring(path.lastIndexOf('/') + 1);
        return segment.isBlank() ? uri.getHost() : segment;
    }

    private static String decodeEntities(String value) {
        return value.replace("&nbsp;", " ")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", "\"")
                .replace("&#39;", "'")
                .replace("&amp;", "&");
    }

    public static String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    public static String normalizeUrl(String value) {
        if (value == null || value.isBlank()) throw new BusinessException(400, "KNOWLEDGE_CRAWL_URL_REQUIRED");
        URI uri;
        try {
            uri = URI.create(value.trim());
        } catch (IllegalArgumentException invalid) {
            throw new BusinessException(400, "KNOWLEDGE_CRAWL_URL_INVALID");
        }
        if (!OutboundUrlPolicy.inspect(uri).allowed()) throw new BusinessException(400, "KNOWLEDGE_CRAWL_URL_BLOCKED");
        String normalized = uri.toString();
        int fragment = normalized.indexOf('#');
        if (fragment >= 0) normalized = normalized.substring(0, fragment);
        if (normalized.length() > MAX_URL) throw new BusinessException(400, "KNOWLEDGE_CRAWL_URL_TOO_LONG");
        return normalized;
    }

    private static boolean isHttpTarget(URI uri) {
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        return scheme.equals("http") || scheme.equals("https");
    }

    private CrawlSource detailSource(Long userId, long sourceId) {
        List<CrawlSource> rows = jdbc.query("SELECT " + SOURCE_COLUMNS + " FROM knowledge_crawl_source WHERE id=? AND user_id=?", this::mapSource, sourceId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "KNOWLEDGE_CRAWL_SOURCE_NOT_FOUND");
        return rows.get(0);
    }

    private CrawlSource mapSource(java.sql.ResultSet rs, int row) throws java.sql.SQLException {
        return new CrawlSource(rs.getLong("id"), rs.getLong("library_id"), rs.getString("name"), rs.getString("seed_url"),
                rs.getInt("max_pages"), rs.getInt("depth"), instant(rs.getTimestamp("last_run_at")),
                rs.getString("last_status"), rs.getString("last_error"), rs.getBoolean("monitor_enabled"),
                rs.getInt("monitor_interval_minutes"), instant(rs.getTimestamp("next_run_at")), instant(rs.getTimestamp("created_at")));
    }

    private static Instant instant(Timestamp value) {
        return value == null ? null : value.toInstant();
    }

    private static void requireActor(SessionUser actor) {
        if (actor == null) throw new BusinessException(401, "登录状态已失效");
    }

    private static int clamp(Integer value, int min, int max, int fallback) {
        if (value == null) return fallback;
        return Math.max(min, Math.min(max, value));
    }

    private static String trimTo(String value, int limit) {
        return value.length() > limit ? value.substring(0, limit) : value;
    }

    /** 去掉 query/fragment：query 里常带 token，且同一页不同 query 不应产生多条知识条目。 */
    public static String stripQuery(String url) {
        try {
            URI uri = URI.create(url);
            return new URI(uri.getScheme(), uri.getAuthority(), uri.getPath(), null, null).toString();
        } catch (Exception invalid) {
            return url;
        }
    }

    /** 只返回我们自己的错误码；原始异常消息可能包含内部主机/端口/IP，不落库。 */
    public static String errorCode(Exception failure) {
        String message = failure.getMessage() == null ? "" : failure.getMessage();
        if (message.startsWith("HTTP ")) return message;
        if (message.contains("下载上限")) return "DOWNLOAD_LIMIT_EXCEEDED";
        if (message.contains("不允许访问")) return "OUTBOUND_BLOCKED";
        if (message.contains("重定向")) return "TOO_MANY_REDIRECTS";
        if (message.equals("地址无效")) return "INVALID_URL";
        if (message.equals("页面没有可提取的正文")) return "EMPTY_CONTENT";
        return "NETWORK_ERROR:" + failure.getClass().getSimpleName();
    }

    private record Link(String url, int depth) {}

    public record CrawlSource(Long id, Long libraryId, String name, String seedUrl, int maxPages, int depth,
                              Instant lastRunAt, String lastStatus, String lastError, boolean monitorEnabled,
                              int monitorIntervalMinutes, Instant nextRunAt, Instant createdAt) {}

    public record CrawlPage(Long id, String url, String title, String contentHash, Long entryId, String changeType, Instant fetchedAt) {}

    public record CrawlResult(int added, int updated, int unchanged, int failed, int pages) {}
}
