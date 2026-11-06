package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.service.VisionHandoffService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/assistant/conversations/{conversationId}/vision-events/{eventId}/handoff")
@RequiredArgsConstructor
public class VisionHandoffController {
    private final VisionHandoffService service;
    @PostMapping("/personal-knowledge") public ApiResponse<?> knowledge(@CurrentUser Long userId, @PathVariable String eventId, @RequestBody KnowledgeRequest request) { return ApiResponse.success(service.toPersonalKnowledge(userId, eventId, request.libraryId(), request.title())); }
    @PostMapping("/memory") public ApiResponse<?> memory(@CurrentUser Long userId, @PathVariable String eventId, @RequestBody MemoryRequest request) { return ApiResponse.success(service.toMemory(userId, eventId, request.incidentKey(), request.action())); }
    public record KnowledgeRequest(Long libraryId, String title) {}
    public record MemoryRequest(String incidentKey, String action) {}
}
