package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.ledger.AgentRunLedgerService;
import com.smartops.security.CurrentUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * Trust Ledger 查询入口（前端信任账本抽屉）。
 *
 * <p>所有读取都按当前登录用户隔离：只能看到自己发起的 Agent 运行。</p>
 */
@RestController
@RequestMapping("/api/agent-ledger")
public class AgentLedgerController {

    private final AgentRunLedgerService service;

    public AgentLedgerController(AgentRunLedgerService service) {
        this.service = service;
    }

    @GetMapping("/runs")
    public ApiResponse<List<Map<String, Object>>> runs(
            @CurrentUser Long userId,
            @RequestParam(defaultValue = "30") int limit) {
        return ApiResponse.success(service.list(userId, limit));
    }

    @GetMapping("/runs/{runId}")
    public ApiResponse<Map<String, Object>> run(@CurrentUser Long userId, @PathVariable String runId) {
        return ApiResponse.success(service.detail(userId, runId));
    }
}
