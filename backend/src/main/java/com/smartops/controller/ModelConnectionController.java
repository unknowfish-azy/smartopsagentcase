package com.smartops.controller;

import com.smartops.dto.model.ModelConnectionCreateRequest;
import com.smartops.dto.model.ModelConnectionResponse;
import com.smartops.dto.model.ModelConnectionUpdateRequest;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.dto.model.RuntimeModelConnectionResponse;
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
            @RequestHeader(
                    value = "X-User-Id",
                    defaultValue = "1"
            )
            Long userId
    ) {

        return ResponseEntity.ok(
                service.list(userId)
        );
    }


    @PostMapping
    public ResponseEntity<ModelConnectionResponse> create(
            @RequestHeader(
                    value = "X-User-Id",
                    defaultValue = "1"
            )
            Long userId,

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
            @RequestHeader(
                    value = "X-User-Id",
                    defaultValue = "1"
            )
            Long userId,

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
            @RequestHeader(
                    value = "X-User-Id",
                    defaultValue = "1"
            )
            Long userId,

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
     * 内部 Runtime 使用。
     *
     * 这里故意不直接返回给前端页面。
     */
    @GetMapping("/{id}/runtime")
    public ResponseEntity<RuntimeModelConnectionResponse> runtime(
            @RequestHeader(
                    value = "X-User-Id",
                    defaultValue = "1"
            )
            Long userId,

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
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long id,
            @Valid @RequestBody ModelInvocationRequest request
    ) {
        return ResponseEntity.ok(service.invoke(userId, id, request));
    }
}
