package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.CurrentUser;
import com.smartops.service.AgentFeedbackService;
import com.smartops.service.AgentFeedbackService.AgentFeedback;
import com.smartops.service.AgentFeedbackService.AgentFeedbackRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Agent 偏好反馈接口（DPO 数据源）。
 * 用户对 AI 回答 / Agent 执行结果点 👍(ADOPTED) / 👎(REJECTED)，沉淀为偏好对。
 */
@RestController
@RequestMapping("/api/agent-feedback")
public class AgentFeedbackController {
    private final AgentFeedbackService service;

    public AgentFeedbackController(AgentFeedbackService service) {
        this.service = service;
    }

    @PostMapping
    public ApiResponse<AgentFeedback> create(@CurrentUser Long userId,
                                             @RequestBody AgentFeedbackRequest request) {
        return ApiResponse.success(service.create(userId, request));
    }

    @GetMapping("/by-run")
    public ApiResponse<List<AgentFeedback>> byRun(@RequestParam String runId,
                                                  @RequestParam(defaultValue = "20") int limit) {
        return ApiResponse.success(service.listByRun(runId, limit));
    }
}
