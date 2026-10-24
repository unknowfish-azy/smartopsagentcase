package com.smartops.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.smartops.common.ApiResponse;
import com.smartops.diagnostics.CertificateProbeService;
import com.smartops.diagnostics.DiagnosticTargetPolicy;
import com.smartops.diagnostics.HttpProbeService;
import com.smartops.security.SessionUser;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/diagnostics")
public class DiagnosticToolController {
    private final DiagnosticTargetPolicy policy;
    private final HttpProbeService http;
    private final CertificateProbeService certificate;
    public DiagnosticToolController(DiagnosticTargetPolicy policy, HttpProbeService http, CertificateProbeService certificate) { this.policy = policy; this.http = http; this.certificate = certificate; }
    @GetMapping("/targets")
    public ApiResponse<?> targets(@AuthenticationPrincipal SessionUser user) { return ApiResponse.success(policy.list(user)); }
    @PostMapping("/http")
    public ApiResponse<HttpProbeService.Result> http(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody HttpRequest request) {
        return ApiResponse.success(http.check(user, new HttpProbeService.Request(request.targetId(), request.method(), request.assertionPath(), request.assertionType(), request.expectedValue())));
    }
    @PostMapping("/certificate")
    public ApiResponse<CertificateProbeService.Result> certificate(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody CertificateRequest request) {
        return ApiResponse.success(certificate.check(user, request.targetId()));
    }
    public record HttpRequest(@NotBlank String targetId, String method, String assertionPath, String assertionType, JsonNode expectedValue) {}
    public record CertificateRequest(@NotBlank String targetId) {}
}
