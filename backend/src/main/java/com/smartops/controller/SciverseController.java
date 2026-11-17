package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.knowledge.SciverseClient;
import com.smartops.knowledge.SciverseKeyStore;
import com.smartops.service.SciverseIngestService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * SciVerse 科学文献蒸馏 API：/api/knowledge/sciverse
 * status = 平台是否已配置；search = 语义检索证据；ingest = 证据蒸馏入库（生成知识候选）；
 * key = 页面手动配置 API Key（运行期热更新 + 持久化到 .env.local 实现长期保存）。
 */
@RestController
@RequestMapping("/api/knowledge/sciverse")
public class SciverseController {

    private final SciverseIngestService service;
    private final SciverseClient client;
    private final SciverseKeyStore keyStore;

    public SciverseController(SciverseIngestService service, SciverseClient client, SciverseKeyStore keyStore) {
        this.service = service;
        this.client = client;
        this.keyStore = keyStore;
    }

    @GetMapping("/status")
    public ApiResponse<SciverseIngestService.SciverseStatus> status() {
        return ApiResponse.success(service.status());
    }

    /**
     * 手动配置 API Key：
     *  1. 校验非空 + sci_ 前缀（官方控制台签发的密钥固定此前缀，sk- 系列会被网关拒绝）；
     *  2. 先持久化（.env.local upsert），再热更新运行中的客户端——落盘成功是「长期保存」的依据；
     *  3. 返回更新后的状态（含脱敏预览），全程不回显完整 Key。
     */
    @PutMapping("/key")
    public ApiResponse<SciverseIngestService.SciverseStatus> updateKey(@RequestBody KeyRequest request) {
        String key = request == null || request.apiKey() == null ? "" : request.apiKey().trim();
        if (key.isEmpty()) {
            return ApiResponse.error(400, "SCIVERSE_KEY_BLANK：密钥不能为空");
        }
        if (!key.startsWith("sci_")) {
            return ApiResponse.error(400, "SCIVERSE_KEY_FORMAT_INVALID：SciVerse 控制台签发的密钥以 sci_ 开头，请到「密钥」页重新复制");
        }
        if (key.length() > 4096) {
            return ApiResponse.error(400, "SCIVERSE_KEY_FORMAT_INVALID：密钥长度异常");
        }
        keyStore.save(key);
        client.setApiKey(key);
        return ApiResponse.success(service.status());
    }

    public record KeyRequest(String apiKey) {}

    @GetMapping("/search")
    public ApiResponse<SciverseIngestService.SciverseSearchResult> search(
            @RequestParam String q,
            @RequestParam(defaultValue = "8") int limit) {
        return ApiResponse.success(service.search(q, limit));
    }

    @PostMapping("/ingest")
    public ApiResponse<SciverseIngestService.SciverseIngestResult> ingest(
            @com.smartops.security.CurrentUser Long userId,
            @RequestBody IngestRequest request) {
        return ApiResponse.success(service.ingest(userId, request.query(), request.indexes(), request.evidences()));
    }

    public record IngestRequest(String query, List<Integer> indexes, List<SciverseIngestService.SciverseEvidence> evidences) {}
}
