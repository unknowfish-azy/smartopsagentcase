package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.service.OperatorMemoryService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/knowledge/memories")
@RequiredArgsConstructor
public class OperatorMemoryController {
    private final OperatorMemoryService service;
    @GetMapping public ApiResponse<?> list(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId) { return ApiResponse.success(service.list(userId)); }
    @GetMapping("/match") public ApiResponse<?> match(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId, @RequestParam String incidentKey) { return ApiResponse.success(service.match(userId, incidentKey)); }
    @PostMapping public ApiResponse<?> create(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId, @RequestBody MemoryRequest request) { return ApiResponse.success(service.recordConfirmed(userId, request.incidentKey(), request.memoryType(), request.preferredAction(), request.sourceRefs())); }
    @PostMapping("/{id}/disable") public ApiResponse<Void> disable(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId, @PathVariable Long id) { service.disable(userId, id); return ApiResponse.success(); }
    @DeleteMapping("/{id}") public ApiResponse<Void> delete(@RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId, @PathVariable Long id) { service.delete(userId, id); return ApiResponse.success(); }
    public record MemoryRequest(String incidentKey, String memoryType, String preferredAction, String sourceRefs) {}
}
