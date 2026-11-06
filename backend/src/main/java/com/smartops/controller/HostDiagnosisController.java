package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.diagnostics.host.HostDiagnosisRequest;
import com.smartops.diagnostics.host.HostDiagnosisService;
import com.smartops.diagnostics.host.HostDiagnosisService.HostDiagnosisResult;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/operations")
public class HostDiagnosisController {

    private final HostDiagnosisService service;

    public HostDiagnosisController(HostDiagnosisService service) {
        this.service = service;
    }

    @PostMapping("/host/diagnose")
    public ApiResponse<HostDiagnosisResult> diagnose(
            @CurrentUser Long userId,
            @Valid @RequestBody HostDiagnosisRequest body) {
        return ApiResponse.success(service.diagnose(userId, body));
    }
}
