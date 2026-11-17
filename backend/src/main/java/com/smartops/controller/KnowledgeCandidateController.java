package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.service.KnowledgeCandidateService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
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
            @CurrentUser Long userId,
            @PathVariable Long runId) {
        return ApiResponse.success(service.createFromRun(userId, runId));
    }

    @PostMapping("/from-web-research/{taskId}")
    public ApiResponse<KnowledgeCandidateService.KnowledgeCandidate> createFromWebResearch(
            @CurrentUser Long userId, @PathVariable Long taskId) {
        return ApiResponse.success(service.createFromWebResearch(userId, taskId));
    }

    /**
     * 日志诊断一键沉淀：body 为 {title, contentMarkdown}，title≤200、contentMarkdown≤20000。
     */
    @PostMapping("/from-log-diagnosis")
    public ApiResponse<KnowledgeCandidateService.KnowledgeCandidate> createFromLogDiagnosis(
            @CurrentUser Long userId,
            @Valid @RequestBody LogDiagnosisRequest request) {
        return ApiResponse.success(service.createFromLogDiagnosis(userId, request.title(), request.contentMarkdown()));
    }

    @GetMapping
    public ApiResponse<KnowledgeCandidateService.KnowledgeCandidatePage> list(
            @CurrentUser Long userId,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.list(userId, status, page, pageSize));
    }

    @GetMapping("/{id}")
    public ApiResponse<KnowledgeCandidateService.KnowledgeCandidate> detail(
            @CurrentUser Long userId,
            @PathVariable Long id) {
        return ApiResponse.success(service.detail(userId, id));
    }

    @PostMapping("/{id}/promote")
    public ApiResponse<com.smartops.service.PersonalKnowledgeService.Entry> promote(
            @CurrentUser Long userId,
            @PathVariable Long id,
            @org.springframework.web.bind.annotation.RequestBody PromoteRequest request) {
        return ApiResponse.success(service.promote(userId, id, request.libraryId(), request.title(), request.contentMarkdown()));
    }

    @PostMapping("/{id}/reject")
    public ApiResponse<Void> reject(
            @CurrentUser Long userId,
            @PathVariable Long id,
            @org.springframework.web.bind.annotation.RequestBody RejectRequest request) {
        service.reject(userId, id, request.reason());
        return ApiResponse.success();
    }

    public record PromoteRequest(Long libraryId, String title, String contentMarkdown) {}
    public record RejectRequest(String reason) {}
    /** 日志诊断一键沉淀请求体：标题与报告正文均有长度上限，防超长文本入库。 */
    public record LogDiagnosisRequest(
            @NotBlank @Size(max = 200) String title,
            @NotBlank @Size(max = 20000) String contentMarkdown) {}
}
