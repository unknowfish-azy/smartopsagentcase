package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.operations.ConnectionResult;
import com.smartops.operations.HostKeyDecision;
import com.smartops.operations.OperationRuntimeRegistry;
import com.smartops.service.OperationConnectionService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/operations")
@RequiredArgsConstructor
public class OperationConnectionController {
    private final OperationConnectionService service;
    private final OperationRuntimeRegistry registry;

    @PostMapping("/sessions/{sessionId}/connect")
    public ApiResponse<ConnectionResult> connect(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long sessionId,
            @RequestParam(defaultValue = "NONE") HostKeyDecision decision) {
        return ApiResponse.success(service.connect(userId, sessionId, decision));
    }

    @DeleteMapping("/runtimes/{runtimeId}")
    public ApiResponse<Void> close(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable String runtimeId) {
        registry.removeOwned(runtimeId, userId).close();
        return ApiResponse.success();
    }
}
