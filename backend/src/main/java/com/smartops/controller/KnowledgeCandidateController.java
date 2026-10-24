package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.service.KnowledgeCandidateService;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestParam;

@RestController
@RequestMapping("/api/knowledge/candidates")
public class KnowledgeCandidateController {
    private final KnowledgeCandidateService service;
    public KnowledgeCandidateController(KnowledgeCandidateService service) { this.service = service; }

    @PostMapping("/from-operation-run/{runId}")
    public ApiResponse<KnowledgeCandidateService.KnowledgeCandidate> createFromOperationRun(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long runId) {
        return ApiResponse.success(service.createFromRun(userId, runId));
    }

    @GetMapping
    public ApiResponse<KnowledgeCandidateService.KnowledgeCandidatePage> list(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.list(userId, status, page, pageSize));
    }

    @GetMapping("/{id}")
    public ApiResponse<KnowledgeCandidateService.KnowledgeCandidate> detail(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long id) {
        return ApiResponse.success(service.detail(userId, id));
    }

    @PostMapping("/{id}/promote")
    public ApiResponse<com.smartops.service.PersonalKnowledgeService.Entry> promote(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long id,
            @org.springframework.web.bind.annotation.RequestBody PromoteRequest request) {
        return ApiResponse.success(service.promote(userId, id, request.libraryId(), request.title(), request.contentMarkdown()));
    }

    @PostMapping("/{id}/reject")
    public ApiResponse<Void> reject(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long id,
            @org.springframework.web.bind.annotation.RequestBody RejectRequest request) {
        service.reject(userId, id, request.reason());
        return ApiResponse.success();
    }

    public record PromoteRequest(Long libraryId, String title, String contentMarkdown) {}
    public record RejectRequest(String reason) {}
}
