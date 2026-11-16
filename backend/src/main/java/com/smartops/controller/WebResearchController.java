package com.smartops.controller;

import com.smartops.assistant.MiniAssistantEngine;
import com.smartops.common.ApiResponse;
import com.smartops.knowledge.WebRenderService;
import com.smartops.knowledge.WebRenderSessionService;
import com.smartops.knowledge.WebResearchEvidenceService;
import com.smartops.knowledge.WebResearchService;
import com.smartops.security.SessionUser;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/web-research")
@RequiredArgsConstructor
public class WebResearchController {
    private final WebResearchService service;
    private final WebRenderService renderService;
    private final WebRenderSessionService renderSessionService;
    private final WebResearchEvidenceService evidenceService;
    private final MiniAssistantEngine miniAssistant;

    @PostMapping("/search")
    public ApiResponse<WebResearchService.SearchResponse> search(@AuthenticationPrincipal SessionUser user,
            @RequestBody SearchRequest request) {
        return ApiResponse.success(service.search(user, request.query(), request.scope(), request.limit()));
    }

    @PostMapping("/fetch")
    public ApiResponse<WebResearchService.WebPage> fetch(@AuthenticationPrincipal SessionUser user,
            @RequestBody FetchRequest request) {
        return ApiResponse.success(service.fetch(user, request.url()));
    }

    @PostMapping("/fetch-js")
    public ApiResponse<WebResearchService.WebPage> fetchJs(@AuthenticationPrincipal SessionUser user,
            @RequestBody FetchRequest request) {
        return ApiResponse.success(renderService.fetchRendered(user, request.url(), true));
    }

    @PostMapping("/render-session/start")
    public ApiResponse<WebRenderSessionService.SessionStatus> startRenderSession(@AuthenticationPrincipal SessionUser user) {
        return ApiResponse.success(renderSessionService.start(user));
    }

    @PostMapping("/render-session/finish")
    public ApiResponse<WebRenderSessionService.SessionStatus> finishRenderSession(@AuthenticationPrincipal SessionUser user) {
        return ApiResponse.success(renderSessionService.finish(user));
    }

    @GetMapping("/render-session")
    public ApiResponse<WebRenderSessionService.SessionStatus> renderSession(@AuthenticationPrincipal SessionUser user) {
        return ApiResponse.success(renderSessionService.status(user));
    }

    @DeleteMapping("/render-session")
    public ApiResponse<WebRenderSessionService.SessionStatus> deleteRenderSession(@AuthenticationPrincipal SessionUser user) {
        renderSessionService.delete(user);
        return ApiResponse.success(new WebRenderSessionService.SessionStatus(false, null, null));
    }

    @GetMapping("/runtime")
    public ApiResponse<MiniAssistantEngine.RuntimeStatus> runtime() {
        return ApiResponse.success(miniAssistant.status());
    }

    @PostMapping("/evidence/compare")
    public ApiResponse<WebResearchEvidenceService.EvidenceComparison> compare(@AuthenticationPrincipal SessionUser user,
            @RequestBody CompareRequest request) {
        return ApiResponse.success(evidenceService.compare(user, request.taskIds()));
    }

    @GetMapping("/tasks")
    public ApiResponse<List<WebResearchService.ResearchTask>> tasks(@AuthenticationPrincipal SessionUser user,
            @RequestParam(defaultValue = "20") int limit) {
        return ApiResponse.success(service.tasks(user, limit));
    }

    public record SearchRequest(String query, String scope, Integer limit) {}
    public record FetchRequest(String url) {}
    public record CompareRequest(List<Long> taskIds) {}
}
