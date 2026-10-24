package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.service.HarborCatalogService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/harbor")
public class HarborCatalogController {
    private final HarborCatalogService service;

    @GetMapping("/status")
    public ApiResponse<HarborCatalogService.SourceStatus> status() {
        return ApiResponse.success(service.status());
    }

    @GetMapping("/connection-check")
    public ApiResponse<HarborCatalogService.ConnectionCheck> checkConnection(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId) {
        return ApiResponse.success(service.checkConnection(userId));
    }

    @GetMapping("/projects/{project}/artifacts")
    public ApiResponse<HarborCatalogService.Page<HarborCatalogService.Artifact>> artifacts(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable String project, @RequestParam String repository,
            @RequestParam(defaultValue = "1") int page) {
        return ApiResponse.success(service.listArtifacts(userId, project, repository, page));
    }

    @GetMapping("/projects")
    public ApiResponse<HarborCatalogService.Page<HarborCatalogService.Project>> projects(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @RequestParam(defaultValue = "1") int page) {
        return ApiResponse.success(service.listProjects(userId, page));
    }

    @GetMapping("/projects/{project}/repositories")
    public ApiResponse<HarborCatalogService.Page<HarborCatalogService.Repository>> repositories(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable String project, @RequestParam(defaultValue = "1") int page) {
        return ApiResponse.success(service.listRepositories(userId, project, page));
    }
}
