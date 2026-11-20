package com.smartops.radar;

import java.time.Instant;
import java.util.List;
import java.util.Set;

/**
 * 资源雷达条目。status 与 score 是两件事：分数只影响排序，状态决定能否被下游使用。
 */
public record RadarItem(Long id, Long sourceId, String sourceName, String channel, String externalId,
                        String title, String summary, String url, String kind, String category, String obtain,
                        int quality, String trustLevel, double freshness, double score, List<String> riskFlags,
                        String status, Instant publishedAt, Instant expiresAt, Instant createdAt) {

    public static final Set<String> STATUSES = Set.of("DRAFT", "VERIFIED", "EXPIRED", "ARCHIVED");
}
