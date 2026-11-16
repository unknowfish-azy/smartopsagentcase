package com.smartops.knowledge;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRedactor;
import com.smartops.security.OutboundUrlPolicy;
import com.smartops.security.SessionUser;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 公开网页与 GitHub 检索。网页内容仅作为不可信证据返回，不进入 Agent 指令链。 */
@Service
public class WebResearchService {
    private static final int MAX_QUERY = 200;
    private static final int MAX_RESULTS = 12;
    private static final int MAX_PAGE_TEXT = 16_000;
    private static final Pattern ANCHOR = Pattern.compile("<a\\b([^>]*)>(.*?)</a>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern HREF = Pattern.compile("\\bhref\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+))", Pattern.CASE_INSENSITIVE);
    private static final Pattern SNIPPET = Pattern.compile("<[^>]+class\\s*=\\s*(?:\"[^\"]*result__snippet[^\"]*\"|'[^']*result__snippet[^']*')[^>]*>(.*?)</[^>]+>",
            Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern GITHUB_REPOSITORY_PATH = Pattern.compile("^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?$");

    private final KnowledgeCrawlService crawler;
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public WebResearchService(KnowledgeCrawlService crawler, JdbcTemplate jdbc, ObjectMapper mapper) {
        this.crawler = crawler;
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    public SearchResponse search(SessionUser actor, String query, String requestedScope, Integer requestedLimit) {
        requireActor(actor);
        String cleaned = cleanQuery(query);
        String scope = requestedScope == null || requestedScope.isBlank()
                ? "ALL" : requestedScope.trim().toUpperCase(Locale.ROOT);
        if (!List.of("ALL", "WEB", "GITHUB").contains(scope)) {
            throw new BusinessException(400, "WEB_RESEARCH_SCOPE_INVALID");
        }
        int limit = clamp(requestedLimit, 1, MAX_RESULTS, 8);
        long taskId = createTask(actor.id(), "SEARCH", cleaned);
        Map<String, SearchResult> results = new LinkedHashMap<>();
        List<String> errors = new ArrayList<>();
        if (scope.equals("ALL") || scope.equals("WEB")) {
            try {
                String endpoint = "https://html.duckduckgo.com/html/?q=" + URLEncoder.encode(cleaned, StandardCharsets.UTF_8);
                String html = crawler.fetch(endpoint, "text/html,application/xhtml+xml");
                for (SearchResult result : parseWebResults(html, limit)) results.putIfAbsent(result.url(), result);
            } catch (InterruptedException failure) {
                Thread.currentThread().interrupt();
                errors.add("WEB:INTERRUPTED");
            } catch (Exception failure) {
                errors.add("WEB:" + KnowledgeCrawlService.errorCode(failure));
            }
        }
        if (!Thread.currentThread().isInterrupted() && (scope.equals("ALL") || scope.equals("GITHUB"))) {
            try {
                String endpoint = "https://api.github.com/search/repositories?q="
                        + URLEncoder.encode(cleaned, StandardCharsets.UTF_8) + "&per_page=" + limit;
                String json = crawler.fetch(endpoint, "application/vnd.github+json,application/json");
                for (SearchResult result : parseGithubResults(json, limit)) results.putIfAbsent(result.url(), result);
            } catch (InterruptedException failure) {
                Thread.currentThread().interrupt();
                errors.add("GITHUB:INTERRUPTED");
            } catch (Exception failure) {
                errors.add("GITHUB:" + KnowledgeCrawlService.errorCode(failure));
            }
        }
        List<SearchResult> items = List.copyOf(results.values());
        String status = items.isEmpty() && !errors.isEmpty() ? "FAILED" : errors.isEmpty() ? "SUCCESS" : "PARTIAL";
        finishTask(taskId, status, items.size(), errors.isEmpty() ? null : trimTo(String.join(";", errors), 500));
        return new SearchResponse(taskId, status, cleaned, scope, items, List.copyOf(errors), Instant.now());
    }

    public WebPage fetch(SessionUser actor, String value) {
        requireActor(actor);
        String url = KnowledgeCrawlService.normalizeUrl(value);
        long taskId = createTask(actor.id(), "FETCH", KnowledgeCrawlService.stripQuery(url));
        try {
            String text;
            String title;
            GithubRepository repository = githubRepository(url);
            if (repository != null) {
                String api = "https://api.github.com/repos/" + repository.owner() + "/" + repository.name();
                JsonNode metadata = mapper.readTree(crawler.fetch(api, "application/vnd.github+json,application/json"));
                String readme = crawler.fetch(api + "/readme", "application/vnd.github.raw+json");
                text = OperationRedactor.redact(trimTo(readme, MAX_PAGE_TEXT));
                String fullName = metadata.path("full_name").asText(repository.owner() + "/" + repository.name());
                title = OperationRedactor.redact(trimTo(fullName + " · README", 200));
            } else {
                String html = crawler.fetch(url);
                text = OperationRedactor.redact(trimTo(KnowledgeCrawlService.htmlToText(html), MAX_PAGE_TEXT));
                title = OperationRedactor.redact(trimTo(KnowledgeCrawlService.pageTitle(html, url), 200));
            }
            if (text.isBlank()) throw new BusinessException(422, "WEB_RESEARCH_EMPTY_CONTENT");
            String hash = KnowledgeCrawlService.sha256(text);
            Instant fetchedAt = Instant.now();
            String displayUrl = KnowledgeCrawlService.stripQuery(url);
            String excerpt = trimTo(text, 600);
            savePageSnapshot(taskId, actor.id(), displayUrl, title, excerpt, text, hash, fetchedAt);
            finishTask(taskId, "SUCCESS", 1, null);
            return new WebPage(taskId, url, displayUrl, host(url), title,
                    excerpt, text, hash, fetchedAt, "STATIC", null);
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            finishTask(taskId, "FAILED", 0, "INTERRUPTED");
            throw new BusinessException(503, "WEB_RESEARCH_INTERRUPTED");
        } catch (BusinessException failure) {
            finishTask(taskId, "FAILED", 0, failure.getMessage());
            throw failure;
        } catch (Exception failure) {
            String code = KnowledgeCrawlService.errorCode(failure);
            finishTask(taskId, "FAILED", 0, code);
            throw new BusinessException(502, "WEB_RESEARCH_FETCH_FAILED:" + code);
        }
    }

    private static GithubRepository githubRepository(String url) {
        try {
            URI uri = URI.create(url);
            if (!"https".equalsIgnoreCase(uri.getScheme()) || !"github.com".equalsIgnoreCase(uri.getHost())) return null;
            Matcher path = GITHUB_REPOSITORY_PATH.matcher(uri.getPath() == null ? "" : uri.getPath());
            return path.matches() ? new GithubRepository(path.group(1), path.group(2)) : null;
        } catch (Exception invalid) {
            return null;
        }
    }

    void savePageSnapshot(long taskId, long userId, String url, String title, String excerpt,
                                  String content, String hash, Instant fetchedAt) {
        jdbc.update("INSERT INTO web_research_page(task_id,user_id,url,title,excerpt,content,content_hash,fetched_at) VALUES(?,?,?,?,?,?,?,?)",
                taskId, userId, url, title, excerpt, content, hash, Timestamp.from(fetchedAt));
    }

    public List<ResearchTask> tasks(SessionUser actor, int requestedLimit) {
        requireActor(actor);
        int limit = Math.max(1, Math.min(50, requestedLimit));
        return jdbc.query("SELECT id,task_type,query_text,status,result_count,error_code,created_at,finished_at FROM web_research_task WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (rs, row) -> new ResearchTask(rs.getLong("id"), rs.getString("task_type"), rs.getString("query_text"),
                        rs.getString("status"), rs.getInt("result_count"), rs.getString("error_code"),
                        instant(rs.getTimestamp("created_at")), instant(rs.getTimestamp("finished_at"))), actor.id(), limit);
    }

    static List<SearchResult> parseWebResults(String html, int requestedLimit) {
        int limit = Math.max(1, Math.min(MAX_RESULTS, requestedLimit));
        Matcher matcher = ANCHOR.matcher(html == null ? "" : html);
        List<AnchorMatch> matches = new ArrayList<>();
        while (matcher.find() && matches.size() < limit) {
            String attributes = matcher.group(1);
            if (!attributes.toLowerCase(Locale.ROOT).contains("result__a")) continue;
            Matcher href = HREF.matcher(attributes);
            if (!href.find()) continue;
            String raw = href.group(1) != null ? href.group(1) : href.group(2) != null ? href.group(2) : href.group(3);
            String url = safeResultUrl(KnowledgeCrawlService.htmlToText(raw == null ? "" : raw));
            if (url == null) continue;
            String title = trimTo(KnowledgeCrawlService.htmlToText(matcher.group(2)), 240);
            matches.add(new AnchorMatch(matcher.start(), matcher.end(), url, title));
        }
        List<SearchResult> results = new ArrayList<>();
        for (int index = 0; index < matches.size(); index++) {
            AnchorMatch match = matches.get(index);
            int end = index + 1 < matches.size() ? matches.get(index + 1).start() : Math.min(html.length(), match.end() + 5_000);
            String region = html.substring(match.end(), Math.max(match.end(), end));
            String snippet = "";
            Matcher snippetMatcher = SNIPPET.matcher(region);
            if (snippetMatcher.find()) snippet = trimTo(KnowledgeCrawlService.htmlToText(snippetMatcher.group(1)), 500);
            results.add(result(match.url(), match.title(), "WEB", snippet, null));
        }
        return results;
    }

    static List<SearchResult> parseGithubResults(String json, int requestedLimit) throws IOException {
        int limit = Math.max(1, Math.min(MAX_RESULTS, requestedLimit));
        JsonNode root = new ObjectMapper().readTree(json);
        List<SearchResult> results = new ArrayList<>();
        for (JsonNode item : root.path("items")) {
            if (results.size() >= limit) break;
            String url = safeResultUrl(item.path("html_url").asText(""));
            if (url == null) continue;
            String title = item.path("full_name").asText(item.path("name").asText("GitHub repository"));
            String description = OperationRedactor.redact(trimTo(item.path("description").asText(""), 500));
            String updatedAt = item.path("updated_at").isTextual() ? item.path("updated_at").asText() : null;
            results.add(result(url, title, "GITHUB", description, updatedAt));
        }
        return results;
    }

    private static SearchResult result(String url, String title, String kind, String snippet, String publishedAt) {
        String site = host(url);
        String safeTitle = OperationRedactor.redact(trimTo(title == null || title.isBlank() ? site : title, 240));
        String id = kind.toLowerCase(Locale.ROOT) + "-" + KnowledgeCrawlService.sha256(url).substring(0, 12);
        return new SearchResult(id, safeTitle, url, KnowledgeCrawlService.stripQuery(url), site,
                OperationRedactor.redact(snippet == null ? "" : snippet), kind, publishedAt, Instant.now());
    }

    private static String safeResultUrl(String raw) {
        if (raw == null || raw.isBlank() || raw.length() > 4_096) return null;
        try {
            String value = raw.trim();
            if (value.startsWith("//")) value = "https:" + value;
            URI uri = URI.create(value);
            if (uri.getHost() != null && uri.getHost().toLowerCase(Locale.ROOT).contains("duckduckgo.com")) {
                String target = queryParameter(uri.getRawQuery(), "uddg");
                if (target != null) {
                    value = URLDecoder.decode(target, StandardCharsets.UTF_8);
                    uri = URI.create(value);
                }
            }
            if (!OutboundUrlPolicy.inspect(uri).allowed()) return null;
            String normalized = uri.toString();
            int fragment = normalized.indexOf('#');
            return fragment >= 0 ? normalized.substring(0, fragment) : normalized;
        } catch (Exception invalid) {
            return null;
        }
    }

    private static String queryParameter(String query, String name) {
        if (query == null) return null;
        for (String pair : query.split("&")) {
            int separator = pair.indexOf('=');
            if (separator > 0 && pair.substring(0, separator).equals(name)) return pair.substring(separator + 1);
        }
        return null;
    }

    long createTask(long userId, String type, String query) {
        GeneratedKeyHolder keys = new GeneratedKeyHolder();
        Instant now = Instant.now();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("INSERT INTO web_research_task(user_id,task_type,query_text,status,result_count,created_at) VALUES(?,?,?,?,0,?)", new String[]{"id"});
            statement.setLong(1, userId);
            statement.setString(2, type);
            statement.setString(3, OperationRedactor.redact(trimTo(query, MAX_QUERY)));
            statement.setString(4, "RUNNING");
            statement.setTimestamp(5, Timestamp.from(now));
            return statement;
        }, keys);
        return keys.getKey().longValue();
    }

    void finishTask(long taskId, String status, int count, String error) {
        jdbc.update("UPDATE web_research_task SET status=?,result_count=?,error_code=?,finished_at=? WHERE id=?",
                status, count, error, Timestamp.from(Instant.now()), taskId);
    }

    private static String cleanQuery(String query) {
        if (query == null || query.isBlank()) throw new BusinessException(400, "WEB_RESEARCH_QUERY_REQUIRED");
        String cleaned = query.trim();
        if (cleaned.length() > MAX_QUERY) throw new BusinessException(400, "WEB_RESEARCH_QUERY_TOO_LONG");
        return cleaned;
    }

    private static String host(String url) {
        try {
            String host = URI.create(url).getHost();
            return host == null ? "unknown" : host.toLowerCase(Locale.ROOT);
        } catch (Exception invalid) {
            return "unknown";
        }
    }

    private static Instant instant(Timestamp value) { return value == null ? null : value.toInstant(); }
    private static int clamp(Integer value, int min, int max, int fallback) { return value == null ? fallback : Math.max(min, Math.min(max, value)); }
    private static String trimTo(String value, int limit) { return value == null ? "" : value.length() > limit ? value.substring(0, limit) : value; }
    private static void requireActor(SessionUser actor) { if (actor == null) throw new BusinessException(401, "登录状态已失效"); }

    private record GithubRepository(String owner, String name) {}
    private record AnchorMatch(int start, int end, String url, String title) {}
    public record SearchResult(String id, String title, String url, String displayUrl, String site, String snippet,
                               String kind, String publishedAt, Instant retrievedAt) {}
    public record SearchResponse(Long taskId, String status, String query, String scope, List<SearchResult> results,
                                 List<String> errors, Instant searchedAt) {}
    public record WebPage(Long taskId, String url, String displayUrl, String site, String title, String excerpt, String content,
                          String contentHash, Instant fetchedAt, String renderMode, String renderNote) {}
    public record ResearchTask(Long id, String taskType, String queryText, String status, int resultCount,
                               String errorCode, Instant createdAt, Instant finishedAt) {}
}
