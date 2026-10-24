package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.dto.ServerCreateRequest;
import com.smartops.dto.ServerUpdateRequest;
import com.smartops.service.ServerService;
import com.smartops.vo.ServerVO;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/servers")
@RequiredArgsConstructor
public class ServerController {

    private final ServerService serverService;

    @PostMapping
    public ApiResponse<ServerVO> create(
            @Valid @RequestBody ServerCreateRequest request) {

        return ApiResponse.success(serverService.create(request));
    }

    @PutMapping("/{id}")
    public ApiResponse<ServerVO> update(
            @PathVariable Long id,
            @Valid @RequestBody ServerUpdateRequest request) {

        return ApiResponse.success(serverService.update(id, request));
    }

    @GetMapping("/{id}")
    public ApiResponse<ServerVO> getById(
            @PathVariable Long id) {

        return ApiResponse.success(serverService.getById(id));
    }

    @GetMapping
    public ApiResponse<List<ServerVO>> list() {

        return ApiResponse.success(serverService.list());
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(
            @PathVariable Long id) {

        serverService.delete(id);

        return ApiResponse.success();
    }
}