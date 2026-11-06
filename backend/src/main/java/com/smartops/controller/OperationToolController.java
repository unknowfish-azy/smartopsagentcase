package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.service.OperationToolService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.List;

@RestController
@RequestMapping("/api/operations")
@RequiredArgsConstructor
public class OperationToolController {
    private final OperationToolService service;

    @GetMapping("/tools")
    public ApiResponse<List<OperationToolService.ToolDescriptor>> tools() {
        return ApiResponse.success(service.listTools());
    }

    @PostMapping("/tools/preview")
    public ApiResponse<OperationToolService.ToolPreview> preview(
            @CurrentUser Long userId,
            @Valid @RequestBody PreviewRequest request) {
        return ApiResponse.success(service.preview(userId, request.toolId(), request.parameters()));
    }

    @PostMapping("/runtimes/{runtimeId}/tools/{toolId}/execute")
    public ApiResponse<OperationToolService.ToolRunResult> execute(
            @CurrentUser Long userId,
            @PathVariable String runtimeId,
            @PathVariable String toolId,
            @Valid @RequestBody ExecuteRequest request) {
        return ApiResponse.success(service.execute(userId, runtimeId, toolId, request.parameters()));
    }

    public record PreviewRequest(@NotBlank String toolId, Map<String, String> parameters) {}
    public record ExecuteRequest(Map<String, String> parameters) {}
}
