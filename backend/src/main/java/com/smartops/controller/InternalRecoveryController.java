package com.smartops.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.smartops.common.ApiResponse;
import com.smartops.recovery.RecoveryContractService;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 恢复契约内部写入接口（agent / 探针侧调用）。
 *
 * <p>只接受 {@code X-SmartOps-Internal-Token}；未配置 token 时过滤器 fail-closed 返回 503，
 * 不允许浏览器会话代替内部身份。写入方必须显式给出 {@code ownerUserId} 与 {@code runId}，
 * 服务层校验 run 归属后才落库。</p>
 */
@RestController
@RequestMapping("/api/internal/recovery/contracts")
public class InternalRecoveryController {

    private final RecoveryContractService service;

    public InternalRecoveryController(RecoveryContractService service) {
        this.service = service;
    }

    @PostMapping
    public ApiResponse<Map<String, Object>> create(@RequestBody JsonNode body) {
        return ApiResponse.success(service.create(body));
    }

    @PostMapping("/{id}/observations")
    public ApiResponse<Map<String, Object>> observations(@PathVariable Long id, @RequestBody JsonNode body) {
        return ApiResponse.success(service.appendObservations(id, body));
    }

    @PostMapping("/{id}/receipts")
    public ApiResponse<Map<String, Object>> receipts(@PathVariable Long id, @RequestBody JsonNode body) {
        return ApiResponse.success(service.appendReceipt(id, body));
    }

    @PostMapping("/{id}/replay-bundles")
    public ApiResponse<Map<String, Object>> replayBundles(@PathVariable Long id, @RequestBody JsonNode body) {
        return ApiResponse.success(service.appendReplayBundle(id, body));
    }
}
