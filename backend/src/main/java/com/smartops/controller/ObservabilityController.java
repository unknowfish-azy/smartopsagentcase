package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.service.ObservabilityService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/observability")
public class ObservabilityController {
    private final ObservabilityService service;

    @GetMapping("/sources")
    public ApiResponse<List<ObservabilityService.SourceStatus>> sources() {
        return ApiResponse.success(service.sources());
    }

    @PostMapping("/{source}/query")
    public ApiResponse<ObservabilityService.QueryResult> query(
            @CurrentUser Long userId,
            @PathVariable String source, @RequestBody QueryRequest request) {
        return ApiResponse.success(service.query(userId, source, request.query(), request.minutes(), request.limit()));
    }

    public record QueryRequest(String query, int minutes, int limit) {}
}
