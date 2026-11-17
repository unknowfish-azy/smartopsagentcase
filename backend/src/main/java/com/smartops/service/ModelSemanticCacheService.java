package com.smartops.service;

import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * 模型网关语义缓存（借鉴 LLM 推理加速中的 Prefix/Semantic Caching 思想）。
 *
 * <p>两级命中策略：</p>
 * <ol>
 *   <li><b>精确命中</b>：hash(group + systemPrompt + prompt + temperature) 完全一致 → 直接返回；</li>
 *   <li><b>语义命中</b>：prompt 归一化（小写、去标点/多余空白）后，与同模型组最近缓存的
 *       prompt 摘要做字符 bigram Jaccard 相似度，≥ 阈值即视为同一意图 → 返回缓存答案。
 *       相似度只在同一 semantic_hash 桶（即相同归一化 system 上下文）内比较，避免跨场景串答案。</li>
 * </ol>
 *
 * <p>设计约束：</p>
 * <ul>
 *   <li>缓存写失败绝不影响主链路（全部内部消化）；</li>
 *   <li>TTL 由 created_at 过滤，写入时顺带清理该组过期条目；</li>
 *   <li>命中回填 hit_count / last_hit_at，供审计观测缓存效率。</li>
 * </ul>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ModelSemanticCacheService {

    private final JdbcTemplate jdbc;

    @Value("${smartops.gateway.cache.enabled:true}")
    private boolean enabled = true;

    @Value("${smartops.gateway.cache.ttl-minutes:60}")
    private int ttlMinutes = 60;

    @Value("${smartops.gateway.cache.similarity-threshold:0.85}")
    private double similarityThreshold = 0.85;

    @Value("${smartops.gateway.cache.candidate-limit:50}")
    private int candidateLimit = 50;

    record CacheRow(Long id, String provider, String model, String content,
                    Integer inputTokens, Integer outputTokens, Integer totalTokens, String digest) {}

    public Optional<ModelInvocationResponse> lookup(Long keyId, String group, ModelInvocationRequest request) {
        if (!enabled || group == null || request == null) return Optional.empty();
        try {
            String digest = normalize(request.getPrompt());
            if (digest.isEmpty()) return Optional.empty();

            String exact = exactHash(group, request);
            String semantic = ModelGatewayService.hash(normalize(request.getSystemPrompt()) + "||" + digest);

            // ── L1：精确命中 ──
            var exactRows = jdbc.query(
                    "SELECT id,provider,model,content,input_tokens,output_tokens,total_tokens,prompt_digest "
                    + "FROM model_semantic_cache WHERE exact_hash=? "
                    + "AND created_at >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL " + Math.max(ttlMinutes, 1) + " MINUTE) LIMIT 1",
                    (rs, n) -> new CacheRow(rs.getLong("id"), rs.getString("provider"), rs.getString("model"),
                            rs.getString("content"), (Integer) rs.getObject("input_tokens"),
                            (Integer) rs.getObject("output_tokens"), (Integer) rs.getObject("total_tokens"),
                            rs.getString("prompt_digest")),
                    exact);
            if (!exactRows.isEmpty()) {
                touch(exactRows.get(0).id());
                return Optional.of(toResponse(exactRows.get(0)));
            }

            // ── L2：语义命中（同 system 桶内 bigram Jaccard）──
            var candidates = jdbc.query(
                    "SELECT id,provider,model,content,input_tokens,output_tokens,total_tokens,prompt_digest "
                    + "FROM model_semantic_cache WHERE group_slug=? AND semantic_hash=? "
                    + "AND created_at >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL " + Math.max(ttlMinutes, 1) + " MINUTE) "
                    + "ORDER BY COALESCE(last_hit_at, created_at) DESC LIMIT " + Math.max(candidateLimit, 1),
                    (rs, n) -> new CacheRow(rs.getLong("id"), rs.getString("provider"), rs.getString("model"),
                            rs.getString("content"), (Integer) rs.getObject("input_tokens"),
                            (Integer) rs.getObject("output_tokens"), (Integer) rs.getObject("total_tokens"),
                            rs.getString("prompt_digest")),
                    group, semantic);
            CacheRow best = null;
            double bestScore = 0.0;
            for (CacheRow row : candidates) {
                String other = row.digest() == null ? "" : row.digest();
                // bigram 抓英文词序，单字符 Jaccard 抓中文插入字差异，取 max
                double score = Math.max(bigramJaccard(digest, other), charJaccard(digest, other));
                if (score > bestScore) { bestScore = score; best = row; }
            }
            if (best != null && bestScore >= similarityThreshold) {
                touch(best.id());
                return Optional.of(toResponse(best));
            }
            return Optional.empty();
        } catch (RuntimeException ex) {
            log.warn("semantic cache lookup failed for group {}: {}", group, ex.getMessage());
            return Optional.empty();
        }
    }

    public void store(Long keyId, String group, ModelInvocationRequest request, ModelInvocationResponse result) {
        if (!enabled || group == null || request == null || result == null) return;
        try {
            String digest = normalize(request.getPrompt());
            if (digest.isEmpty() || result.getContent() == null || result.getContent().isBlank()) return;
            long id = newId();
            String exact = exactHash(group, request);
            String semantic = ModelGatewayService.hash(normalize(request.getSystemPrompt()) + "||" + digest);
            jdbc.update("DELETE FROM model_semantic_cache WHERE exact_hash=?", exact);
            jdbc.update("INSERT INTO model_semantic_cache(id,group_slug,exact_hash,semantic_hash,prompt_digest,"
                            + "provider,model,content,input_tokens,output_tokens,total_tokens) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    id, group, exact, semantic, truncate(digest, 1900), result.getProvider(), result.getModel(),
                    result.getContent(), intOf(result.getUsage(), "prompt_tokens"),
                    intOf(result.getUsage(), "completion_tokens"), intOf(result.getUsage(), "total_tokens"));
            // 顺带清理本组过期条目，避免表无限增长
            jdbc.update("DELETE FROM model_semantic_cache WHERE group_slug=? "
                    + "AND created_at < DATE_SUB(CURRENT_TIMESTAMP, INTERVAL " + Math.max(ttlMinutes, 1) + " MINUTE)", group);
        } catch (RuntimeException ex) {
            log.warn("semantic cache store failed for group {}: {}", group, ex.getMessage());
        }
    }

    /* ── 内部工具 ───────────────────────────────────────── */

    private void touch(Long id) {
        try {
            jdbc.update("UPDATE model_semantic_cache SET hit_count=hit_count+1, last_hit_at=CURRENT_TIMESTAMP WHERE id=?", id);
        } catch (RuntimeException ex) {
            log.warn("semantic cache touch failed: {}", ex.getMessage());
        }
    }

    private ModelInvocationResponse toResponse(CacheRow row) {
        Map<String, Object> usage = new HashMap<>();
        if (row.inputTokens() != null) usage.put("prompt_tokens", row.inputTokens().longValue());
        if (row.outputTokens() != null) usage.put("completion_tokens", row.outputTokens().longValue());
        if (row.totalTokens() != null) usage.put("total_tokens", row.totalTokens().longValue());
        return ModelInvocationResponse.builder()
                .provider(row.provider()).model(row.model()).content(row.content()).usage(usage)
                .build();
    }

    private String exactHash(String group, ModelInvocationRequest request) {
        String temp = request.getTemperature() == null ? "" : request.getTemperature().toString();
        return ModelGatewayService.hash(group + "|" + nullSafe(request.getSystemPrompt()) + "|" + nullSafe(request.getPrompt()) + "|" + temp);
    }

    /** 归一化：小写、剔除标点/符号/多余空白，供语义比较。保留 CJK。 */
    static String normalize(String text) {
        if (text == null) return "";
        return text.toLowerCase().replaceAll("[\\p{P}\\p{S}\\s]+", " ").trim();
    }

    /** 字符 bigram Jaccard 相似度：改写过的同义问题也能命中。 */
    static double bigramJaccard(String a, String b) {
        if (a.equals(b)) return 1.0;
        Set<String> ga = bigrams(a), gb = bigrams(b);
        if (ga.isEmpty() || gb.isEmpty()) return 0.0;
        int inter = 0;
        for (String g : ga) if (gb.contains(g)) inter++;
        int union = ga.size() + gb.size() - inter;
        return union == 0 ? 0.0 : (double) inter / union;
    }

    /** 单字符 Jaccard：对中文少字/多字改写（如插入"的"）比 bigram 更稳。 */
    static double charJaccard(String a, String b) {
        if (a.equals(b)) return 1.0;
        if (a.isEmpty() || b.isEmpty()) return 0.0;
        Set<Character> ca = new HashSet<>(), cb = new HashSet<>();
        for (int i = 0; i < a.length(); i++) ca.add(a.charAt(i));
        for (int i = 0; i < b.length(); i++) cb.add(b.charAt(i));
        int inter = 0;
        for (Character c : ca) if (cb.contains(c)) inter++;
        int union = ca.size() + cb.size() - inter;
        return union == 0 ? 0.0 : (double) inter / union;
    }

    private static Set<String> bigrams(String s) {
        Set<String> out = new HashSet<>();
        for (int i = 0; i < s.length() - 1; i++) out.add(s.substring(i, i + 2));
        return out;
    }

    private static String nullSafe(String v) { return v == null ? "" : v; }
    private static String truncate(String v, int max) { return v.length() <= max ? v : v.substring(0, max); }
    private static Integer intOf(Map<String, Object> usage, String key) {
        Object v = usage == null ? null : usage.get(key);
        return v instanceof Number n ? n.intValue() : null;
    }
    private long newId() { return SecureRandomLong.next(); }

    /** 独立长整型 id 生成器，避免引入额外状态字段。 */
    static final class SecureRandomLong {
        private static final java.security.SecureRandom R = new java.security.SecureRandom();
        static long next() { return R.nextLong() & Long.MAX_VALUE; }
    }
}
