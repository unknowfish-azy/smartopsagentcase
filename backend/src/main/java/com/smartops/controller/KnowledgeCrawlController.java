package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.knowledge.WebResearchEvidenceService;
import com.smartops.knowledge.KnowledgeCrawlService;
import com.smartops.security.SessionUser;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/knowledge/crawl")
@RequiredArgsConstructor
public class KnowledgeCrawlController {
    private final KnowledgeCrawlService service;
    private final WebResearchEvidenceService evidenceService;

    @GetMapping("/sources")
    public ApiResponse<java.util.List<KnowledgeCrawlService.CrawlSource>> sources(@AuthenticationPrincipal SessionUser user) {
        return ApiResponse.success(service.listSources(user));
    }

    @PostMapping("/sources")
    public ApiResponse<KnowledgeCrawlService.CrawlSource> create(@AuthenticationPrincipal SessionUser user, @RequestBody SourceRequest request) {
        return ApiResponse.success(service.createSource(user, request.libraryId(), request.name(), request.seedUrl(), request.maxPages(), request.depth()));
    }

    @PostMapping("/sources/{sourceId}/run")
    public ApiResponse<KnowledgeCrawlService.CrawlResult> run(@AuthenticationPrincipal SessionUser user, @PathVariable long sourceId) {
        return ApiResponse.success(service.run(user, sourceId));
    }

    @PatchMapping("/sources/{sourceId}/monitor")
    public ApiResponse<KnowledgeCrawlService.CrawlSource> monitor(@AuthenticationPrincipal SessionUser user,
            @PathVariable long sourceId, @RequestBody MonitorRequest request) {
        return ApiResponse.success(service.updateMonitor(user, sourceId, request.enabled(), request.intervalMinutes()));
    }

    @GetMapping("/sources/{sourceId}/pages")
    public ApiResponse<java.util.List<KnowledgeCrawlService.CrawlPage>> pages(@AuthenticationPrincipal SessionUser user, @PathVariable long sourceId, @RequestParam(defaultValue = "20") int limit) {
        return ApiResponse.success(service.listPages(user, sourceId, limit));
    }

    @GetMapping("/pages/{pageId}/diff")
    public ApiResponse<WebResearchEvidenceService.CrawlPageDiff> diff(@AuthenticationPrincipal SessionUser user, @PathVariable long pageId) {
        return ApiResponse.success(evidenceService.diffCrawlPage(user, pageId));
    }

    public record SourceRequest(Long libraryId, String name, String seedUrl, Integer maxPages, Integer depth) {}
    public record MonitorRequest(boolean enabled, Integer intervalMinutes) {}
}
