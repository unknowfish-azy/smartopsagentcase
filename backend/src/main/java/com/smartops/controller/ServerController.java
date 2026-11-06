package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.dto.ServerCreateRequest;
import com.smartops.dto.ServerUpdateRequest;
import com.smartops.security.SessionUser;
import com.smartops.service.ServerService;
import com.smartops.vo.ServerVO;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/servers")
@RequiredArgsConstructor
public class ServerController {

    private final ServerService serverService;

    @PostMapping
    public ApiResponse<ServerVO> create(
            @AuthenticationPrincipal SessionUser actor,
            @Valid @RequestBody ServerCreateRequest request) {

        return ApiResponse.success(serverService.create(actor, request));
    }

    @PutMapping("/{id}")
    public ApiResponse<ServerVO> update(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable Long id,
            @Valid @RequestBody ServerUpdateRequest request) {

        return ApiResponse.success(serverService.update(actor, id, request));
    }

    @GetMapping("/{id}")
    public ApiResponse<ServerVO> getById(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable Long id) {

        return ApiResponse.success(serverService.getById(actor, id));
    }

    @GetMapping
    public ApiResponse<List<ServerVO>> list(
            @AuthenticationPrincipal SessionUser actor) {

        return ApiResponse.success(serverService.list(actor));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable Long id) {

        serverService.delete(actor, id);

        return ApiResponse.success();
    }
}
