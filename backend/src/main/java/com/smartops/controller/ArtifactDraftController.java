package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.service.ArtifactDraftService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/knowledge/artifacts")
@RequiredArgsConstructor
public class ArtifactDraftController {
    private final ArtifactDraftService service;
    @GetMapping public ApiResponse<?> list(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId) { return ApiResponse.success(service.list(userId)); }
    @PostMapping public ApiResponse<?> create(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId, @RequestBody DraftRequest request) { return ApiResponse.success(service.createDraft(userId, request.type(), request.title(), request.content(), request.sourceRef(), request.risk())); }
    @PostMapping("/{id}/submit-review") public ApiResponse<?> submit(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId, @PathVariable Long id) { return ApiResponse.success(service.submitReview(userId, id)); }
    public record DraftRequest(String type, String title, String content, String sourceRef, String risk) {}
}
