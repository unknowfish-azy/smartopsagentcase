package com.smartops.service;

import com.smartops.knowledge.SciverseClient;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * SciverseIngestService — SciVerse 科学文献蒸馏编排
 *
 * 管线（对齐 SciVerse 文档的 Sci-Base 能力）：
 *  1. agentic-search 语义检索证据片段（带原文定位）；
 *  2. 证据入 knowledge_candidate（PENDING_REVIEW），零伪造红线——
 *     平台返回什么就存什么，不做二次改写；
 *  3. 人工在知识候选审核页 promote 后进入个人知识库（复用既有闸门）。
 */
@Service
public class SciverseIngestService {

    public record SciverseStatus(boolean configured, String baseUrl, String keyPreview, boolean persistent) {}

    /** 前端展示用证据项：索引号用于「蒸馏入库」时回传。 */
    public record SciverseEvidence(int index, String docId, String title, String locator, String text) {}

    public record SciverseSearchResult(boolean configured, List<SciverseEvidence> evidences, String notice) {}

    public record SciverseIngestResult(int requested, int created, int duplicated, List<Long> candidateIds, String notice) {}

    private final SciverseClient client;
    private final KnowledgeCandidateService candidates;
    private final com.smartops.knowledge.SciverseKeyStore keyStore;

    public SciverseIngestService(SciverseClient client, KnowledgeCandidateService candidates,
                                 com.smartops.knowledge.SciverseKeyStore keyStore) {
        this.client = client;
        this.candidates = candidates;
        this.keyStore = keyStore;
    }

    public SciverseStatus status() {
        return new SciverseStatus(client.configured(), client.baseUrl(), client.keyPreview(), keyStore.persisted());
    }

    public SciverseSearchResult search(String query, int limit) {
        if (query == null || query.isBlank()) {
            return new SciverseSearchResult(client.configured(), List.of(), "请输入蒸馏主题");
        }
        try {
            List<SciverseClient.Evidence> evidences = client.search(query, limit);
            List<SciverseEvidence> items = new ArrayList<>();
            for (int i = 0; i < evidences.size(); i++) {
                SciverseClient.Evidence evidence = evidences.get(i);
                items.add(new SciverseEvidence(i + 1, evidence.docId(), evidence.title(), evidence.locator(), evidence.text()));
            }
            String notice = items.isEmpty() ? "平台未返回证据片段，可调整检索式后重试" : null;
            return new SciverseSearchResult(true, items, notice);
        } catch (SciverseClient.SciverseNotConfiguredException failure) {
            return new SciverseSearchResult(false, List.of(), failure.getMessage());
        }
    }

    /** 把检索到的证据蒸馏入库：一条证据 = 一个知识候选（幂等）。 */
    public SciverseIngestResult ingest(Long userId, String query, List<Integer> indexes, List<SciverseEvidence> evidences) {
        Instant now = Instant.now();
        int created = 0;
        int duplicated = 0;
        List<Long> ids = new ArrayList<>();
        for (SciverseEvidence evidence : evidences) {
            if (evidence == null || evidence.text() == null || evidence.text().isBlank()) continue;
            KnowledgeCandidateService.KnowledgeCandidate candidate = candidates.createFromSciverse(
                    userId, query, evidence.docId(), evidence.title(), evidence.locator(), evidence.text(), now);
            // 幂等收敛后拿到的候选若创建时间早于本次调用，视为重复命中。
            if (candidate.createdAt() != null && candidate.createdAt().isBefore(now.minusSeconds(2))) duplicated++;
            else created++;
            ids.add(candidate.id());
        }
        String notice = created == 0 && duplicated > 0 ? "所选证据均已蒸馏入库过，无新增候选" : null;
        return new SciverseIngestResult(evidences.size(), created, duplicated, ids, notice);
    }
}
