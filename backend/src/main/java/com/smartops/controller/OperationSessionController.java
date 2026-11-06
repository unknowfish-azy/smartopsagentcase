package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.dto.operations.CreateOperationSessionRequest;
import com.smartops.dto.operations.OperationSessionResponse;
import com.smartops.service.OperationSessionService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/operations/sessions")
@RequiredArgsConstructor
public class OperationSessionController {
    private final OperationSessionService service;

    @GetMapping
    public ApiResponse<List<OperationSessionResponse>> list(@CurrentUser Long userId) { return ApiResponse.success(service.list(userId)); }

    @PostMapping
    public ApiResponse<OperationSessionResponse> create(@CurrentUser Long userId, @Valid @RequestBody CreateOperationSessionRequest request) { return ApiResponse.success(service.create(userId, request)); }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@CurrentUser Long userId, @PathVariable Long id) { service.delete(userId, id); return ApiResponse.success(); }
}
