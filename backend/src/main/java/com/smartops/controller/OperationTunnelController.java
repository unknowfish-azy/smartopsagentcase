package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.service.OperationTunnelService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/operations/runtimes/{runtimeId}/tunnels")
@RequiredArgsConstructor
public class OperationTunnelController {
    private final OperationTunnelService service;

    @PostMapping
    public ApiResponse<String> start(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
                                    @PathVariable String runtimeId,
                                    @RequestParam String name,
                                    @RequestParam(defaultValue = "127.0.0.1") String listenAddress,
                                    @RequestParam int listenPort,
                                    @RequestParam String targetHost,
                                    @RequestParam int targetPort) {
        return ApiResponse.success(service.start(userId, runtimeId, name, listenAddress, listenPort, targetHost, targetPort));
    }

    @DeleteMapping("/{tunnelId}")
    public ApiResponse<Void> stop(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
                                  @PathVariable String runtimeId,
                                  @PathVariable String tunnelId) {
        service.stop(userId, runtimeId, tunnelId);
        return ApiResponse.success();
    }
}
