package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.dto.MetricCreateRequest;
import com.smartops.security.SessionUser;
import com.smartops.service.ServerMetricService;
import com.smartops.service.ServerService;
import com.smartops.vo.ServerMetricVO;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/servers/{serverId}/metrics")
@RequiredArgsConstructor
public class ServerMetricController {

    private final ServerMetricService metricService;
    private final ServerService serverService;

    @PostMapping
    public ApiResponse<ServerMetricVO> create(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable Long serverId,
            @Valid @RequestBody MetricCreateRequest request) {

        // SEC-08：指标是资产子资源，先校验资产归属，再做读写。
        serverService.requireAccessible(actor, serverId);
        return ApiResponse.success(
                metricService.create(serverId, request)
        );
    }

    @GetMapping("/latest")
    public ApiResponse<ServerMetricVO> latest(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable Long serverId) {

        serverService.requireAccessible(actor, serverId);
        return ApiResponse.success(
                metricService.latest(serverId)
        );
    }

    @GetMapping
    public ApiResponse<List<ServerMetricVO>> list(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable Long serverId) {

        serverService.requireAccessible(actor, serverId);
        return ApiResponse.success(
                metricService.latestList(serverId)
        );
    }
}
