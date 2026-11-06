package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.diagnostics.kubernetes.KubernetesDiagnosisRequest;
import com.smartops.diagnostics.kubernetes.KubernetesDiagnosisService;
import com.smartops.diagnostics.kubernetes.KubernetesDiagnosisService.KubernetesDiagnosisResult;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/operations")
public class KubernetesDiagnosisController {

    private final KubernetesDiagnosisService service;

    public KubernetesDiagnosisController(KubernetesDiagnosisService service) {
        this.service = service;
    }

    @PostMapping("/kubernetes/diagnose")
    public ApiResponse<KubernetesDiagnosisResult> diagnose(
            @CurrentUser Long userId,
            @Valid @RequestBody DiagnoseRequest body) {
        KubernetesDiagnosisRequest request = new KubernetesDiagnosisRequest(
                body.context(), body.namespace(), body.workload(), body.pod(), body.container(),
                body.sinceMinutes());
        return ApiResponse.success(service.diagnose(userId, body.runtimeId(), request));
    }

    public record DiagnoseRequest(@NotBlank String runtimeId, @NotBlank String context,
                                  @NotBlank String namespace, String workload, String pod,
                                  String container, int sinceMinutes) {}
}
