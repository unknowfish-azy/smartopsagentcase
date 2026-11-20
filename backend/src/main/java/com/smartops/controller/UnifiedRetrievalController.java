package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.CurrentUser;
import com.smartops.service.UnifiedRetrievalService;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 统一检索 REST 端点（P0-1）。
 *
 * <p>聚合情景记忆、个人知识库、共享知识库的检索入口，
 * 替代分散的 match/search 接口，为 Agent 提供单一 RAG 检索面。
 */
@RestController
@RequestMapping("/api/retrieval")
public class UnifiedRetrievalController {

    private final UnifiedRetrievalService retrieval;

    public UnifiedRetrievalController(UnifiedRetrievalService retrieval) {
        this.retrieval = retrieval;
    }

    /**
     * 统一检索。
     *
     * @param query       检索文本
     * @param collections 可选，指定集合（MEMORY、PERSONAL_KNOWLEDGE、SHARED_KNOWLEDGE），空为全部
     * @param limit       返回上限，默认 10
     */
    @GetMapping("/search")
    public ApiResponse<?> search(@CurrentUser Long userId,
                                 @RequestParam String query,
                                 @RequestParam(required = false) List<String> collections,
                                 @RequestParam(defaultValue = "10") int limit) {
        return ApiResponse.success(retrieval.search(userId, query, collections, limit));
    }
}
