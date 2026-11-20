package com.smartops.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.smartops.common.ApiResponse;
import com.smartops.ledger.AgentRunLedgerService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Agent 运行账本内部写入接口（ai-service 在每次 run 结束后回传真实结果）。
 *
 * <p>只接受 {@code X-SmartOps-Internal-Token}；未配置 token 时过滤器 fail-closed 返回 503。
 * 用户归属由 ai-service 从 Java 签发的 run 令牌 subject 解析后显式给出，浏览器会话无法伪造。</p>
 */
@RestController
@RequestMapping("/api/internal/agent-ledger")
public class InternalAgentLedgerController {

    private final AgentRunLedgerService service;

    public InternalAgentLedgerController(AgentRunLedgerService service) {
        this.service = service;
    }

    @PostMapping("/runs")
    public ApiResponse<Map<String, Object>> record(@RequestBody JsonNode body) {
        return ApiResponse.success(service.record(body));
    }
}
