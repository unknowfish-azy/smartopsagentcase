package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.service.VisionEventService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/assistant/conversations/{conversationId}/vision-events")
@RequiredArgsConstructor
public class VisionEventController {
    private final VisionEventService service;
    @PostMapping("/from-attachment/{attachmentId}") public ApiResponse<?> create(@CurrentUser Long userId, @PathVariable String conversationId, @PathVariable String attachmentId, @RequestParam(defaultValue = "FILE") String sourceType) { return ApiResponse.success(service.create(userId, conversationId, attachmentId, sourceType)); }
    @GetMapping public ApiResponse<?> list(@CurrentUser Long userId, @PathVariable String conversationId) { return ApiResponse.success(service.list(userId, conversationId)); }
    @GetMapping("/{id}") public ApiResponse<?> detail(@CurrentUser Long userId, @PathVariable String id) { return ApiResponse.success(service.detail(userId, id)); }
    @PostMapping("/{id}/ocr") public ApiResponse<?> ocr(@CurrentUser Long userId, @PathVariable String id, @RequestBody OcrRequest request) { return ApiResponse.success(analysis.recordOcr(userId, id, request.text(), request.confidence())); }
    @PostMapping("/{id}/confirm") public ApiResponse<?> confirm(@CurrentUser Long userId, @PathVariable String id) { return ApiResponse.success(service.confirm(userId, id)); }
    private final com.smartops.service.VisionAnalysisService analysis;
    public record OcrRequest(String text, double confidence) {}
}
