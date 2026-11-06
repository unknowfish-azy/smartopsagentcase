package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.service.OperationAgentContextService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/operations/runtimes/{runtimeId}/agent-context")
@RequiredArgsConstructor
public class OperationAgentContextController {
    private final OperationAgentContextService service;

    @GetMapping
    public ApiResponse<OperationAgentContextService.Context> get(
            @CurrentUser Long userId,
            @PathVariable String runtimeId) {
        return ApiResponse.success(service.get(userId, runtimeId));
    }
}
