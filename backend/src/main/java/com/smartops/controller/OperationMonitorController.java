package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.operations.ServerMonitorSample;
import com.smartops.operations.ServerMonitorService;
import com.smartops.security.CurrentUser;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 真实监控采样端点：runtime 归属校验与文件端点同款（requireOwned）。 */
@RestController
@RequestMapping("/api/operations/runtimes/{runtimeId}/monitor")
@RequiredArgsConstructor
public class OperationMonitorController {

    private final ServerMonitorService service;

    @GetMapping
    public ApiResponse<ServerMonitorSample> monitor(@CurrentUser Long userId, @PathVariable String runtimeId) {
        return ApiResponse.success(service.sample(userId, runtimeId));
    }
}
