package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.diagnostics.HealthDiagnosticService;
import com.smartops.security.SessionUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/diagnostics")
public class HealthDiagnosticController {
    private final HealthDiagnosticService service;
    public HealthDiagnosticController(HealthDiagnosticService service) { this.service = service; }
    @GetMapping("/health")
    public ApiResponse<HealthDiagnosticService.Summary> health(@AuthenticationPrincipal SessionUser user) { return ApiResponse.success(service.summary(user)); }
    @GetMapping("/admin/health")
    public ApiResponse<HealthDiagnosticService.Summary> adminHealth(@AuthenticationPrincipal SessionUser user) { return ApiResponse.success(service.adminSummary(user)); }
}
