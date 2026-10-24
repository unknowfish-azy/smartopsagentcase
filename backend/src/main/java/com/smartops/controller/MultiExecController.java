package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.service.MultiExecService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/operations/multi-exec")
@RequiredArgsConstructor
public class MultiExecController {
    private final MultiExecService service;

    @PostMapping("/preview")
    public ApiResponse<MultiExecService.Preview> preview(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @Valid @RequestBody PreviewRequest request) {
        return ApiResponse.success(service.preview(userId, request.command(), request.runtimeIds(), request.productionTarget()));
    }

    @PostMapping("/execute")
    public ApiResponse<MultiExecService.ExecutionResult> execute(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @Valid @RequestBody ExecuteRequest request) {
        return ApiResponse.success(service.execute(userId, request.previewId(), request.confirmationNonce(), request.secondConfirmationNonce()));
    }

    public record PreviewRequest(@NotBlank String command, @NotEmpty List<String> runtimeIds, boolean productionTarget) {}
    public record ExecuteRequest(@NotBlank String previewId, @NotBlank String confirmationNonce, String secondConfirmationNonce) {}
}
