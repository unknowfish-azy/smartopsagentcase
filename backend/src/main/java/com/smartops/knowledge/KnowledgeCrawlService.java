package com.smartops.knowledge;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.service.PersonalKnowledgeService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 知识库爬取：把一个同域静态站点抓成个人知识库条目。
 *
 * <p>抓取过程是同步的，网络请求不包事务；每页独立落库，单页失败不影响整轮。</p>
 */
@Service
public class KnowledgeCrawlService {
    private static final String USER_AGENT = "SmartOpsAgent-KnowledgeCrawler/1.0";
    private static final int MAX_CONTENT = 20_000;
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
    private static final String SOURCE_COLUMNS = "id,library_id,name,seed_url,max_pages,depth,last_run_at,last_status,last_error,created_at";

    private final JdbcTemplate jdbc;
    private final PersonalKnowledgeService knowledge;
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    public KnowledgeCrawlService(JdbcTemplate jdbc, PersonalKnowledgeService knowledge) {
        this.jdbc = jdbc;
        this.knowledge = knowledge;
    }

    public CrawlSource createSource(SessionUser actor, Long libraryId, String name, String seedUrl, Integer maxPages, Integer depth) {
        requireActor(actor);
        if (libraryId == null) throw new BusinessException(400, "KNOWLEDGE_CRAWL_LIBRARY_REQUIRED");
        knowledge.detailLibrary(actor.id(), libraryId);
        if (name == null || name.isBlank()) throw new BusinessException(400, "KNOWLEDGE_CRAWL_NAME_REQUIRED");
        String url = normalizeUrl(seedUrl);
        int pages = clamp(maxPages, 1, 50, 20);
        int level = clamp(depth, 0, 2, 1);
        jdbc.update("INSERT INTO knowledge_crawl_source(user_id,library_id,name,seed_url,max_pages,depth,created_at) VALUES(?,?,?,?,?,?,?)",
                actor.id(), libraryId, trimTo(name.trim(), 120), url, pages, level, Timestamp.from(Instant.now()));
        Long id = jdbc.queryForObject("SELECT MAX(id) FROM knowledge_crawl_source WHERE user_id=?", Long.class, actor.id());
        return detailSource(actor.id(), id);
    }

    public List<CrawlSource> listSources(SessionUser actor) {
        requireActor(actor);
        return jdbc.query("SELECT " + SOURCE_COLUMNS + " FROM knowledge_crawl_source WHERE user_id=? ORDER BY id DESC", this::mapSource, actor.id());
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
        CrawlSource source = detailSource(actor.id(), sourceId);
        URI seed = URI.create(source.seedUrl());
        String seedHost = seed.getHost();
        Deque<Link> queue = new ArrayDeque<>();
        Set<String> visited = new LinkedHashSet<>();
        queue.add(new Link(source.seedUrl(), 0));
        visited.add(source.seedUrl());
        int added = 0, updated = 0, unchanged = 0, failed = 0, pages = 0;
        List<String> errors = new ArrayList<>();
        while (!queue.isEmpty() && pages < source.maxPages()) {
            Link link = queue.poll();
            pages++;
            try {
                String html = fetch(link.url());
                String text = trimTo(htmlToText(html), MAX_CONTENT);
                if (text.isBlank()) throw new IOException("页面没有可提取的正文");
                String hash = sha256(text);
                String title = trimTo(pageTitle(html, link.url()), 200);
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
                errors.add(link.url() + " 抓取被中断");
                break;
            } catch (Exception failure) {
                failed++;
                errors.add(link.url() + " " + messageOf(failure));
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
        jdbc.update("UPDATE knowledge_crawl_source SET last_run_at=?,last_status=?,last_error=? WHERE id=? AND user_id=?",
                Timestamp.from(Instant.now()), status, trimTo(String.join("；", errors), 500), sourceId, actor.id());
        return new CrawlResult(added, updated, unchanged, failed, pages);
    }

    private String persist(SessionUser actor, CrawlSource source, String url, String title, String text, String hash) {
        List<Long> existing = jdbc.query("SELECT id FROM personal_knowledge_entry WHERE user_id=? AND library_id=? AND source_ref=? LIMIT 1",
                (rs, row) -> rs.getLong(1), actor.id(), source.libraryId(), url);
        String summary = trimTo(text, 160);
        long entryId;
        String change;
        if (existing.isEmpty()) {
            entryId = knowledge.createEntry(actor.id(), source.libraryId(), title, summary, text, "web_crawl", url).id();
            change = "ADDED";
        } else {
            entryId = existing.get(0);
            String lastHash = jdbc.query("SELECT content_hash FROM knowledge_crawl_page WHERE source_id=? AND url=? ORDER BY id DESC LIMIT 1",
                    (rs, row) -> rs.getString(1), source.id(), url).stream().findFirst().orElse(null);
            if (lastHash != null && lastHash.equals(hash)) {
                change = "UNCHANGED";
            } else {
                knowledge.updateEntry(actor.id(), entryId, title, summary, text);
                change = "UPDATED";
            }
        }
        jdbc.update("INSERT INTO knowledge_crawl_page(source_id,user_id,url,title,content_md,content_hash,entry_id,change_type,fetched_at) VALUES(?,?,?,?,?,?,?,?,?)",
                source.id(), actor.id(), url, title, text, hash, entryId, change, Timestamp.from(Instant.now()));
        return change;
    }

    private String fetch(String url) throws IOException, InterruptedException {
        String current = url;
        for (int hop = 0; hop < 4; hop++) {
            URI uri;
            try {
                uri = URI.create(current);
            } catch (IllegalArgumentException invalid) {
                throw new IOException("地址无效");
            }
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(8))
                    .header("User-Agent", USER_AGENT)
                    .header("Accept", "text/html,application/xhtml+xml")
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            int code = response.statusCode();
            if (code >= 200 && code < 300) return response.body();
            String location = response.headers().firstValue("Location").orElse(null);
            // 重定向目标同样要过内网校验，避免借跳转绕过 host 白名单
            if (code >= 300 && code < 400 && location != null) {
                URI target = uri.resolve(location);
                if (!publicTarget(target)) throw new IOException("重定向到不允许的地址");
                current = target.toString();
                continue;
            }
            throw new IOException("HTTP " + code);
        }
        throw new IOException("重定向次数过多");
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
            if (!publicTarget(resolved) || seedHost == null || !seedHost.equalsIgnoreCase(resolved.getHost())) continue;
            String normalized = resolved.toString();
            int fragment = normalized.indexOf('#');
            if (fragment >= 0) normalized = normalized.substring(0, fragment);
            if (normalized.length() > MAX_URL || ASSET.matcher(normalized).matches()) continue;
            links.add(normalized);
        }
        return links;
    }

    private static String htmlToText(String html) {
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

    private static String pageTitle(String html, String url) {
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

    private static String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static String normalizeUrl(String value) {
        if (value == null || value.isBlank()) throw new BusinessException(400, "KNOWLEDGE_CRAWL_URL_REQUIRED");
        URI uri;
        try {
            uri = URI.create(value.trim());
        } catch (IllegalArgumentException invalid) {
            throw new BusinessException(400, "KNOWLEDGE_CRAWL_URL_INVALID");
        }
        if (!publicTarget(uri)) throw new BusinessException(400, "KNOWLEDGE_CRAWL_URL_BLOCKED");
        String normalized = uri.toString();
        int fragment = normalized.indexOf('#');
        if (fragment >= 0) normalized = normalized.substring(0, fragment);
        if (normalized.length() > MAX_URL) throw new BusinessException(400, "KNOWLEDGE_CRAWL_URL_TOO_LONG");
        return normalized;
    }

    private static boolean publicTarget(URI uri) {
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) return false;
        String host = uri.getHost();
        if (host == null || host.isBlank()) return false;
        String value = host.toLowerCase(Locale.ROOT).replace("[", "").replace("]", "");
        if (value.equals("localhost") || value.endsWith(".localhost") || value.equals("::1") || value.equals("0.0.0.0")) return false;
        if (value.startsWith("127.") || value.startsWith("169.254.") || value.startsWith("10.") || value.startsWith("192.168.")) return false;
        return !value.matches("172\\.(1[6-9]|2\\d|3[01])\\..*");
    }

    private CrawlSource detailSource(Long userId, long sourceId) {
        List<CrawlSource> rows = jdbc.query("SELECT " + SOURCE_COLUMNS + " FROM knowledge_crawl_source WHERE id=? AND user_id=?", this::mapSource, sourceId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "KNOWLEDGE_CRAWL_SOURCE_NOT_FOUND");
        return rows.get(0);
    }

    private CrawlSource mapSource(java.sql.ResultSet rs, int row) throws java.sql.SQLException {
        return new CrawlSource(rs.getLong("id"), rs.getLong("library_id"), rs.getString("name"), rs.getString("seed_url"),
                rs.getInt("max_pages"), rs.getInt("depth"), instant(rs.getTimestamp("last_run_at")),
                rs.getString("last_status"), rs.getString("last_error"), instant(rs.getTimestamp("created_at")));
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

    private static String messageOf(Exception failure) {
        String message = failure.getMessage();
        return message == null || message.isBlank() ? failure.getClass().getSimpleName() : message;
    }

    private record Link(String url, int depth) {}

    public record CrawlSource(Long id, Long libraryId, String name, String seedUrl, int maxPages, int depth,
                              Instant lastRunAt, String lastStatus, String lastError, Instant createdAt) {}

    public record CrawlPage(Long id, String url, String title, String contentHash, Long entryId, String changeType, Instant fetchedAt) {}

    public record CrawlResult(int added, int updated, int unchanged, int failed, int pages) {}
}
