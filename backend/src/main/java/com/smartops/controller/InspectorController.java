package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.dto.inspector.InspectionRecordRequest;
import com.smartops.dto.inspector.InspectionReplanRequest;
import com.smartops.dto.inspector.InspectionVerifyRequest;
import com.smartops.service.InspectorEventService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/inspector")
@RequiredArgsConstructor
public class InspectorController {

    private final InspectorEventService service;

    @GetMapping("/summary")
    public ApiResponse<Map<String, Object>> summary() {
        return ApiResponse.success(service.summary());
    }

    @GetMapping("/events")
    public ApiResponse<List<Map<String, Object>>> events(
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(service.events(limit));
    }

    @GetMapping("/events/{id}")
    public ApiResponse<Map<String, Object>> event(@PathVariable String id) {
        return ApiResponse.success(service.event(id));
    }

    @PostMapping("/check")
    public ApiResponse<Map<String, Object>> check(
            @Valid @RequestBody InspectionRecordRequest request) {
        return ApiResponse.success(service.record(request));
    }

    @PostMapping("/verify")
    public ApiResponse<Map<String, Object>> verify(
            @Valid @RequestBody InspectionVerifyRequest request) {
        return ApiResponse.success(service.verify(request));
    }

    @PostMapping("/replan")
    public ApiResponse<Map<String, Object>> replan(
            @Valid @RequestBody InspectionReplanRequest request) {
        return ApiResponse.success(service.replan(request));
    }

    @GetMapping("/statistics")
    public ApiResponse<Map<String, Object>> statistics() {
        return ApiResponse.success(service.statistics());
    }
}
