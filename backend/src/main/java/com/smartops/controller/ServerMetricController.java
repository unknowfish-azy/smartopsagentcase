package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.dto.MetricCreateRequest;
import com.smartops.service.ServerMetricService;
import com.smartops.vo.ServerMetricVO;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/servers/{serverId}/metrics")
@RequiredArgsConstructor
public class ServerMetricController {

    private final ServerMetricService metricService;

    @PostMapping
    public ApiResponse<ServerMetricVO> create(
            @PathVariable Long serverId,
            @Valid @RequestBody MetricCreateRequest request) {

        return ApiResponse.success(
                metricService.create(serverId, request)
        );
    }

    @GetMapping("/latest")
    public ApiResponse<ServerMetricVO> latest(
            @PathVariable Long serverId) {

        return ApiResponse.success(
                metricService.latest(serverId)
        );
    }

    @GetMapping
    public ApiResponse<List<ServerMetricVO>> list(
            @PathVariable Long serverId) {

        return ApiResponse.success(
                metricService.latestList(serverId)
        );
    }
}