package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.diagnostics.network.NetworkPathRequest;
import com.smartops.diagnostics.network.NetworkPathService;
import com.smartops.diagnostics.network.NetworkPathService.NetworkPathResult;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/operations")
public class NetworkPathDiagnosisController {

    private final NetworkPathService service;

    public NetworkPathDiagnosisController(NetworkPathService service) {
        this.service = service;
    }

    @PostMapping("/network/diagnose")
    public ApiResponse<NetworkPathResult> diagnose(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @Valid @RequestBody DiagnoseRequest body) {
        NetworkPathRequest request = new NetworkPathRequest(
                body.context(), body.namespace(), body.host(), body.port(), body.service(), body.ingress(),
                body.workload(), body.tls(), body.timeoutSeconds());
        return ApiResponse.success(service.diagnose(userId, body.runtimeId(), request));
    }

    public record DiagnoseRequest(@NotBlank String runtimeId, @NotBlank String context,
                                  @NotBlank String namespace, String host, int port, String service,
                                  String ingress, String workload, boolean tls, int timeoutSeconds) {}
}
