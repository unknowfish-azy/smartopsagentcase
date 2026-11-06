package com.smartops.controller;

import com.smartops.dto.model.ModelConnectionCreateRequest;
import com.smartops.dto.model.ModelConnectionResponse;
import com.smartops.dto.model.ModelConnectionUpdateRequest;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.dto.model.RuntimeModelConnectionResponse;
import com.smartops.security.CurrentUser;
import com.smartops.service.ModelConnectionService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/model-connections")
@RequiredArgsConstructor
public class ModelConnectionController {

    private final ModelConnectionService service;


    @GetMapping
    public ResponseEntity<List<ModelConnectionResponse>> list(
            @CurrentUser Long userId
    ) {

        return ResponseEntity.ok(
                service.list(userId)
        );
    }


    @PostMapping
    public ResponseEntity<ModelConnectionResponse> create(
            @CurrentUser Long userId,

            @Valid
            @RequestBody
            ModelConnectionCreateRequest request
    ) {

        return ResponseEntity.ok(
                service.create(
                        userId,
                        request
                )
        );
    }


    @PutMapping("/{id}")
    public ResponseEntity<ModelConnectionResponse> update(
            @CurrentUser Long userId,

            @PathVariable
            Long id,

            @Valid
            @RequestBody
            ModelConnectionUpdateRequest request
    ) {

        return ResponseEntity.ok(
                service.update(
                        userId,
                        id,
                        request
                )
        );
    }


    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(
            @CurrentUser Long userId,

            @PathVariable
            Long id
    ) {

        service.delete(
                userId,
                id
        );

        return ResponseEntity.noContent()
                .build();
    }


    /**
     * 内部 Runtime 使用（internal token 通道）。
     *
     * 这里故意不直接返回给前端页面；userId 由调用方（持内部 token 的后端服务）显式传入，
     * 不再提供 {@code defaultValue = "1"} 的回落——缺失即为 400。
     */
    @GetMapping("/{id}/runtime")
    public ResponseEntity<RuntimeModelConnectionResponse> runtime(
            @RequestHeader("X-User-Id") Long userId,

            @PathVariable
            Long id
    ) {

        return ResponseEntity.ok(
                service.getRuntimeConfiguration(
                        userId,
                        id
                )
        );
    }

    @PostMapping("/{id}/invoke")
    public ResponseEntity<ModelInvocationResponse> invoke(
            @RequestHeader("X-User-Id") Long userId,
            @PathVariable Long id,
            @Valid @RequestBody ModelInvocationRequest request
    ) {
        return ResponseEntity.ok(service.invoke(userId, id, request));
    }
}
