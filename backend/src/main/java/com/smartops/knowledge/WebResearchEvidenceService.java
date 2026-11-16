package com.smartops.knowledge;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** 对服务端已有网页快照做确定性证据分析，不调用模型，也不自动判断事实真假。 */
@Service
public class WebResearchEvidenceService {
    private static final int MAX_COMPARE_PAGES = 4;
    private static final int MAX_DIFF_LINES = 400;
    private static final int FIELD_PREVIEW = 600;
    private static final int SHINGLE_SIZE = 8;
    private final JdbcTemplate jdbc;

    public WebResearchEvidenceService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public EvidenceComparison compare(SessionUser actor, List<Long> taskIds) {
        requireActor(actor);
        LinkedHashSet<Long> uniqueIds = validatedTaskIds(taskIds);
        List<PageSnapshot> pages = uniqueIds.stream().map(taskId -> loadPage(actor.id(), taskId)).toList();
        List<EvidenceItem> items = pages.stream().map(WebResearchEvidenceService::assessment).toList();
        List<PairOverlap> pairs = new ArrayList<>();
        for (int left = 0; left < pages.size(); left++) {
            for (int right = left + 1; right < pages.size(); right++) {
                PageSnapshot first = pages.get(left);
                PageSnapshot second = pages.get(right);
                double overlap = textOverlap(first.content(), second.content());
                boolean differentHosts = !first.site().equals("unknown") && !first.site().equals(second.site());
                pairs.add(new PairOverlap(first.taskId(), second.taskId(), differentHosts, overlap,
                        overlapLevel(overlap),
                        "文本重合只作为人工核验线索，不证明事实一致、来源独立或内容真实。"));
            }
        }
        return new EvidenceComparison(items, List.copyOf(pairs),
                "来源信号和文本重合度不替代原文核验，不构成真实性评分或事实裁决。", Instant.now());
    }

    public CrawlPageDiff diffCrawlPage(SessionUser actor, long pageId) {
        requireActor(actor);
        List<CrawlSnapshot> currentRows = jdbc.query(
                "SELECT id,source_id,user_id,url,title,content_md,content_hash,change_type,fetched_at FROM knowledge_crawl_page WHERE id=? AND user_id=?",
                (rs, row) -> crawlSnapshot(rs), pageId, actor.id());
        if (currentRows.isEmpty()) throw new BusinessException(404, "KNOWLEDGE_CRAWL_PAGE_NOT_FOUND");
        CrawlSnapshot current = currentRows.get(0);
        List<CrawlSnapshot> previousRows = jdbc.query(
                "SELECT id,source_id,user_id,url,title,content_md,content_hash,change_type,fetched_at FROM knowledge_crawl_page WHERE source_id=? AND user_id=? AND url=? AND id<? ORDER BY id DESC LIMIT 1",
                (rs, row) -> crawlSnapshot(rs), current.sourceId(), actor.id(), current.url(), current.id());
        if (previousRows.isEmpty()) {
            return new CrawlPageDiff(current.id(), null, current.url(), false,
                    List.of(), List.of(), false, "这是该地址的首个快照，没有可比较的更早版本。");
        }
        CrawlSnapshot previous = previousRows.get(0);
        List<FieldDiff> fields = List.of(
                field("title", "标题", previous.title(), current.title()),
                field("content", "正文（预览）", previous.content(), current.content()),
                field("contentHash", "正文 SHA-256", previous.contentHash(), current.contentHash()));
        LineComputation computation = lineDiff(previous.content(), current.content());
        String note = "按相邻快照展示字段和正文行差异，不自动判断哪个版本正确。"
                + (computation.truncated() ? " 正文行差异仅计算各自前 " + MAX_DIFF_LINES + " 行，完整版本仍以快照和哈希为准。" : "");
        return new CrawlPageDiff(current.id(), previous.id(), current.url(), true,
                fields, computation.lines(), computation.truncated(), note);
    }

    private PageSnapshot loadPage(long userId, long taskId) {
        List<PageSnapshot> rows = jdbc.query(
                "SELECT p.task_id,p.url,p.title,p.content,p.content_hash,p.fetched_at,t.task_type FROM web_research_page p "
                        + "JOIN web_research_task t ON t.id=p.task_id AND t.user_id=p.user_id WHERE p.user_id=? AND p.task_id=?",
                (rs, row) -> {
                    String url = rs.getString("url");
                    return new PageSnapshot(rs.getLong("task_id"), rs.getString("task_type"), url, host(url),
                            rs.getString("title"), rs.getString("content"), rs.getString("content_hash"),
                            instant(rs.getTimestamp("fetched_at")));
                }, userId, taskId);
        if (rows.isEmpty()) throw new BusinessException(404, "WEB_RESEARCH_PAGE_NOT_FOUND");
        return rows.get(0);
    }

    private static EvidenceItem assessment(PageSnapshot page) {
        boolean https = page.url() != null && page.url().toLowerCase(Locale.ROOT).startsWith("https://");
        boolean hashMatches = page.contentHash() != null
                && KnowledgeCrawlService.sha256(page.content()).equalsIgnoreCase(page.contentHash());
        boolean provenanceComplete = hashMatches && page.fetchedAt() != null;
        List<EvidenceSignal> signals = List.of(
                new EvidenceSignal("TRANSPORT", https ? "PASS" : "WARN", "传输协议",
                        https ? "使用 HTTPS；证书与域名归属仍需在原文中核验。" : "未使用 HTTPS，传输完整性保护较弱。"),
                new EvidenceSignal("PROVENANCE", provenanceComplete ? "PASS" : "WARN", "快照完整性",
                        provenanceComplete ? "服务端正文与 SHA-256 匹配，并记录任务和抓取时间。" : "正文哈希或抓取时间需要复核。"),
                new EvidenceSignal("CONTENT", page.content().isBlank() ? "WARN" : "PASS", "正文可读性",
                        "服务端快照包含 " + page.content().length() + " 个字符；长度不代表质量。"),
                new EvidenceSignal("PUBLICATION_TIME", "UNKNOWN", "内容发布时间",
                        "当前快照只有抓取时间，不能把抓取时间当成内容发布时间。"),
                new EvidenceSignal("SOURCE_AUTHORITY", "UNKNOWN", "作者与域名归属",
                        "未核验作者、机构或域名归属，不自动认定为官方来源。"));
        return new EvidenceItem(page.taskId(), page.taskType(), page.title(), page.url(), page.site(),
                page.contentHash(), page.fetchedAt(), page.content().length(), signals);
    }

    private static LinkedHashSet<Long> validatedTaskIds(List<Long> taskIds) {
        if (taskIds == null) throw new BusinessException(400, "WEB_RESEARCH_COMPARE_SIZE");
        LinkedHashSet<Long> ids = new LinkedHashSet<>();
        for (Long taskId : taskIds) {
            if (taskId == null || taskId <= 0) throw new BusinessException(400, "WEB_RESEARCH_TASK_INVALID");
            ids.add(taskId);
            if (ids.size() > MAX_COMPARE_PAGES) throw new BusinessException(400, "WEB_RESEARCH_COMPARE_SIZE");
        }
        if (ids.size() < 2) throw new BusinessException(400, "WEB_RESEARCH_COMPARE_SIZE");
        return ids;
    }

    static double textOverlap(String left, String right) {
        Set<String> first = shingles(left);
        Set<String> second = shingles(right);
        if (first.isEmpty() || second.isEmpty()) return 0;
        Set<String> intersection = new HashSet<>(first);
        intersection.retainAll(second);
        Set<String> union = new HashSet<>(first);
        union.addAll(second);
        double value = union.isEmpty() ? 0 : (double) intersection.size() / union.size();
        return Math.round(value * 10_000d) / 10_000d;
    }

    private static Set<String> shingles(String value) {
        String normalized = normalize(value);
        Set<String> shingles = new HashSet<>();
        if (normalized.isBlank()) return shingles;
        if (normalized.length() <= SHINGLE_SIZE) {
            shingles.add(normalized);
            return shingles;
        }
        for (int index = 0; index <= normalized.length() - SHINGLE_SIZE; index++) {
            shingles.add(normalized.substring(index, index + SHINGLE_SIZE));
        }
        return shingles;
    }

    private static String normalize(String value) {
        if (value == null) return "";
        StringBuilder normalized = new StringBuilder();
        value.toLowerCase(Locale.ROOT).codePoints()
                .filter(Character::isLetterOrDigit)
                .forEach(normalized::appendCodePoint);
        return normalized.toString();
    }

    private static String overlapLevel(double overlap) {
        if (overlap >= 0.75) return "HIGH";
        if (overlap >= 0.25) return "PARTIAL";
        return "LOW";
    }

    private static FieldDiff field(String field, String label, String before, String after) {
        String safeBefore = before == null ? "" : before;
        String safeAfter = after == null ? "" : after;
        return new FieldDiff(field, label, trimTo(safeBefore, FIELD_PREVIEW), trimTo(safeAfter, FIELD_PREVIEW),
                !safeBefore.equals(safeAfter), safeBefore.length() > FIELD_PREVIEW || safeAfter.length() > FIELD_PREVIEW);
    }

    static LineComputation lineDiff(String before, String after) {
        List<String> oldLines = Arrays.asList((before == null ? "" : before).split("\\R", -1));
        List<String> newLines = Arrays.asList((after == null ? "" : after).split("\\R", -1));
        boolean truncated = oldLines.size() > MAX_DIFF_LINES || newLines.size() > MAX_DIFF_LINES;
        oldLines = oldLines.subList(0, Math.min(MAX_DIFF_LINES, oldLines.size()));
        newLines = newLines.subList(0, Math.min(MAX_DIFF_LINES, newLines.size()));
        int oldSize = oldLines.size();
        int newSize = newLines.size();
        int[][] lcs = new int[oldSize + 1][newSize + 1];
        for (int oldIndex = oldSize - 1; oldIndex >= 0; oldIndex--) {
            for (int newIndex = newSize - 1; newIndex >= 0; newIndex--) {
                lcs[oldIndex][newIndex] = oldLines.get(oldIndex).equals(newLines.get(newIndex))
                        ? lcs[oldIndex + 1][newIndex + 1] + 1
                        : Math.max(lcs[oldIndex + 1][newIndex], lcs[oldIndex][newIndex + 1]);
            }
        }
        List<LineDiff> lines = new ArrayList<>();
        int oldIndex = 0, newIndex = 0;
        while (oldIndex < oldSize && newIndex < newSize) {
            if (oldLines.get(oldIndex).equals(newLines.get(newIndex))) {
                lines.add(new LineDiff("CONTEXT", oldLines.get(oldIndex), oldIndex + 1, newIndex + 1));
                oldIndex++;
                newIndex++;
            } else if (lcs[oldIndex + 1][newIndex] >= lcs[oldIndex][newIndex + 1]) {
                lines.add(new LineDiff("REMOVED", oldLines.get(oldIndex++), oldIndex, 0));
            } else {
                lines.add(new LineDiff("ADDED", newLines.get(newIndex++), 0, newIndex));
            }
        }
        while (oldIndex < oldSize) lines.add(new LineDiff("REMOVED", oldLines.get(oldIndex++), oldIndex, 0));
        while (newIndex < newSize) lines.add(new LineDiff("ADDED", newLines.get(newIndex++), 0, newIndex));
        return new LineComputation(List.copyOf(lines), truncated);
    }

    private static CrawlSnapshot crawlSnapshot(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new CrawlSnapshot(rs.getLong("id"), rs.getLong("source_id"), rs.getLong("user_id"),
                rs.getString("url"), rs.getString("title"), rs.getString("content_md"),
                rs.getString("content_hash"), rs.getString("change_type"), instant(rs.getTimestamp("fetched_at")));
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
    private static String trimTo(String value, int limit) { return value.length() > limit ? value.substring(0, limit) : value; }
    private static void requireActor(SessionUser actor) { if (actor == null) throw new BusinessException(401, "登录状态已失效"); }

    private record PageSnapshot(long taskId, String taskType, String url, String site, String title, String content,
                                String contentHash, Instant fetchedAt) {}
    private record CrawlSnapshot(long id, long sourceId, long userId, String url, String title, String content,
                                 String contentHash, String changeType, Instant fetchedAt) {}

    public record EvidenceComparison(List<EvidenceItem> items, List<PairOverlap> pairs,
                                     String disclaimer, Instant comparedAt) {}
    public record EvidenceItem(long taskId, String taskType, String title, String url, String site,
                               String contentHash, Instant fetchedAt, int contentLength, List<EvidenceSignal> signals) {}
    public record EvidenceSignal(String code, String state, String label, String detail) {}
    public record PairOverlap(long leftTaskId, long rightTaskId, boolean differentHosts,
                              double textOverlap, String overlapLevel, String note) {}
    public record CrawlPageDiff(long pageId, Long previousPageId, String url, boolean hasPrevious,
                                List<FieldDiff> fields, List<LineDiff> lines, boolean truncated, String note) {}
    public record FieldDiff(String field, String label, String before, String after,
                            boolean changed, boolean valueTruncated) {}
    public record LineDiff(String type, String text, int beforeLine, int afterLine) {}
    record LineComputation(List<LineDiff> lines, boolean truncated) {}
}
