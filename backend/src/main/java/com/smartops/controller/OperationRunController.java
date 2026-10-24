package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.service.OperationRunQueryService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;

@RestController
@RequestMapping("/api/operations/runs")
public class OperationRunController {
    private final OperationRunQueryService service;
    public OperationRunController(OperationRunQueryService service) { this.service = service; }

    @GetMapping
    public ApiResponse<OperationRunQueryService.RunPage> list(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @RequestParam(required = false) String traceId,
            @RequestParam(required = false) String toolId,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant startedFrom,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant startedTo,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.list(userId, traceId, toolId, status, startedFrom, startedTo, page, pageSize));
    }

    @GetMapping("/{id}")
    public ApiResponse<OperationRunQueryService.RunDetail> detail(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long id) {
        return ApiResponse.success(service.detail(userId, id));
    }
}
