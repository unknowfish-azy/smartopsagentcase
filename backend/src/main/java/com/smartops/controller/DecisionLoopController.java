package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.service.DecisionLoopService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * AI 运维决策闭环接口：分析 → 记忆 → 决策 → 复盘 → 学习回写。
 */
@RestController
@RequestMapping("/api/agent/loops")
@RequiredArgsConstructor
public class DecisionLoopController {

    private final DecisionLoopService service;

    @GetMapping
    public ApiResponse<?> list(
            @CurrentUser Long userId,
            @RequestParam(defaultValue = "30") int limit) {
        return ApiResponse.success(service.list(userId, limit));
    }

    @GetMapping("/stats")
    public ApiResponse<?> stats(@CurrentUser Long userId) {
        return ApiResponse.success(service.stats(userId));
    }

    @GetMapping("/{id}")
    public ApiResponse<?> detail(
            @CurrentUser Long userId,
            @PathVariable String id) {
        return ApiResponse.success(service.detail(userId, id));
    }

    @PostMapping
    public ApiResponse<?> create(
            @CurrentUser Long userId,
            @RequestBody DecisionLoopService.CreateRequest request) {
        return ApiResponse.success(service.create(userId, request));
    }

    @PostMapping("/{id}/recall")
    public ApiResponse<?> recall(
            @CurrentUser Long userId,
            @PathVariable String id) {
        return ApiResponse.success(service.recall(userId, id));
    }

    @PostMapping("/{id}/decide")
    public ApiResponse<?> decide(
            @CurrentUser Long userId,
            @PathVariable String id,
            @RequestBody DecisionLoopService.DecideRequest request) {
        return ApiResponse.success(service.decide(userId, id, request));
    }

    @PostMapping("/{id}/review")
    public ApiResponse<?> review(
            @CurrentUser Long userId,
            @PathVariable String id,
            @RequestBody DecisionLoopService.ReviewRequest request) {
        return ApiResponse.success(service.review(userId, id, request));
    }
}
