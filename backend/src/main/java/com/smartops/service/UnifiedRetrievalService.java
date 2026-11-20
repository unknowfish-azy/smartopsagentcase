package com.smartops.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/**
 * 统一语义检索接口（P0-1）。
 *
 * <p>把分散的检索入口（情景记忆、个人知识、共享知识）聚合为单一接口，
 * 提供分集合路由、元数据过滤、相关度打分与低置信度拒答。
 *
 * <p><strong>实现说明</strong>：当前版本使用关键词重叠打分作为占位实现。
 * 真正的 BM25+向量融合需要接入 embedding 服务（bge-m3 / Kimi Embedding），
 * 那是独立向量服务的职责，不在本服务内伪造。
 * 接入点已预留在 {@link #score} 方法，替换为真实向量余弦相似度即可。
 *
 * <p><strong>隔离红线</strong>：
 * <ul>
 *   <li>未审核的 operator_memory（PENDING_REVIEW/REJECTED）不进入召回；</li>
 *   <li>未验证的 personal_knowledge_entry（UNVERIFIED）默认不进入召回；</li>
 *   <li>knowledge_candidate 不进入正式检索——它们是待审核原料，不是知识。</li>
 * </ul>
 */
@Service
public class UnifiedRetrievalService {

    /** 低置信度拒答阈值：所有结果最高分低于此值时返回空。 */
    private static final double LOW_CONFIDENCE_THRESHOLD = 0.15d;

    private final JdbcTemplate jdbc;

    public UnifiedRetrievalService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * 统一检索入口。
     *
     * @param userId      当前用户（隔离边界）
     * @param query       检索文本
     * @param collections 要检索的集合，空表示全部；
     *                    可选值：MEMORY、PERSONAL_KNOWLEDGE、SHARED_KNOWLEDGE
     * @param limit       返回条数上限
     * @return 检索结果，含低置信度标记
     */
    public RetrievalResponse search(Long userId, String query, List<String> collections, int limit) {
        if (query == null || query.isBlank()) {
            return new RetrievalResponse(List.of(), false, "EMPTY_QUERY");
        }
        int capped = Math.max(1, Math.min(limit, 50));
        List<String> scopes = (collections == null || collections.isEmpty())
                ? List.of("MEMORY", "PERSONAL_KNOWLEDGE", "SHARED_KNOWLEDGE")
                : collections;

        List<RetrievalItem> items = new ArrayList<>();
        if (scopes.contains("MEMORY")) items.addAll(searchMemory(userId, query));
        if (scopes.contains("PERSONAL_KNOWLEDGE")) items.addAll(searchPersonalKnowledge(userId, query));
        if (scopes.contains("SHARED_KNOWLEDGE")) items.addAll(searchSharedKnowledge(query));

        // 按相关度 × 置信度排序，截断到 limit
        List<RetrievalItem> ranked = items.stream()
                .sorted(Comparator.comparingDouble((RetrievalItem item) -> item.relevance * item.confidence).reversed())
                .limit(capped)
                .toList();

        // 低置信度拒答：最高分仍低于阈值时不返回任何结果
        boolean lowConfidence = ranked.isEmpty()
                || ranked.stream().mapToDouble(item -> item.relevance * item.confidence).max().orElse(0) < LOW_CONFIDENCE_THRESHOLD;

        return new RetrievalResponse(lowConfidence ? List.of() : ranked, lowConfidence,
                lowConfidence ? "LOW_CONFIDENCE" : "OK");
    }

    /** 情景记忆召回：只查 ACTIVE，PENDING_REVIEW/REJECTED 被隔离。 */
    private List<RetrievalItem> searchMemory(Long userId, String query) {
        List<RetrievalItem> items = new ArrayList<>();
        jdbc.query(
                "SELECT id,incident_key,preferred_action,confidence,memory_type FROM operator_memory " +
                        "WHERE user_id=? AND status='ACTIVE'",
                rs -> {
                    String key = rs.getString("incident_key");
                    String action = rs.getString("preferred_action");
                    double confidence = rs.getDouble("confidence");
                    double relevance = score(query, key + " " + action);
                    if (relevance > 0) {
                        items.add(new RetrievalItem(
                                "MEMORY", rs.getLong("id"), key, action,
                                relevance, confidence, rs.getString("memory_type")));
                    }
                }, userId);
        return items;
    }

    /** 个人知识库：只查 VERIFIED（已审核验证）条目。 */
    private List<RetrievalItem> searchPersonalKnowledge(Long userId, String query) {
        List<RetrievalItem> items = new ArrayList<>();
        jdbc.query(
                "SELECT id,title,summary,content_markdown,source_type FROM personal_knowledge_entry " +
                        "WHERE user_id=? AND verification_status='VERIFIED'",
                rs -> {
                    String title = rs.getString("title");
                    String summary = rs.getString("summary");
                    String content = rs.getString("content_markdown");
                    double relevance = score(query, title + " " + summary + " " + content);
                    if (relevance > 0) {
                        items.add(new RetrievalItem(
                                "PERSONAL_KNOWLEDGE", rs.getLong("id"), title, summary,
                                relevance, 0.8d, rs.getString("source_type")));
                    }
                }, userId);
        return items;
    }

    /** 共享知识库：已经过 promote 审核，全员可见。 */
    private List<RetrievalItem> searchSharedKnowledge(String query) {
        List<RetrievalItem> items = new ArrayList<>();
        jdbc.query(
                "SELECT id,title,summary,content_markdown,source_type FROM shared_knowledge_entry",
                rs -> {
                    String title = rs.getString("title");
                    String summary = rs.getString("summary");
                    String content = rs.getString("content_markdown");
                    double relevance = score(query, title + " " + summary + " " + content);
                    if (relevance > 0) {
                        items.add(new RetrievalItem(
                                "SHARED_KNOWLEDGE", rs.getLong("id"), title, summary,
                                relevance, 0.85d, rs.getString("source_type")));
                    }
                });
        return items;
    }

    /**
     * 相关度打分：关键词重叠率。
     *
     * <p>占位实现：计算 query 中关键词在文本中的命中比例。
     * 接入真实 embedding 服务后，此方法应替换为
     * {@code cosine_similarity(embed(query), embed(text))}，
     * 或 BM25 与向量分的加权融合。
     */
    static double score(String query, String text) {
        if (query == null || text == null) return 0;
        String q = query.toLowerCase(Locale.ROOT).trim();
        String t = text.toLowerCase(Locale.ROOT);
        if (q.isEmpty() || t.isEmpty()) return 0;

        // 整串包含：满分
        if (t.contains(q)) return 1.0;

        // 分词重叠
        String[] tokens = q.split("[\\s,，。.、;；:：!！?？]+");
        int hits = 0;
        int total = 0;
        for (String token : tokens) {
            if (token.length() < 2) continue;
            total++;
            if (t.contains(token)) hits++;
        }
        return total == 0 ? 0 : (double) hits / total;
    }

    /** 单条检索结果。 */
    public record RetrievalItem(
            String collection, Long id, String title, String snippet,
            double relevance, double confidence, String sourceType) {}

    /** 检索响应。 */
    public record RetrievalResponse(List<RetrievalItem> items, boolean lowConfidence, String status) {}
}
