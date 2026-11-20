package com.smartops.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.smartops.common.ApiResponse;
import com.smartops.exception.BusinessException;
import com.smartops.service.AgentTriggerService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * W7：事件驱动的内部触发入口。
 *
 * <p>只接受 {@code X-SmartOps-Internal-Token}（浏览器会话无法伪造）；
 * 5 分钟单资源防抖、只读白名单与"模型不可用不产事件"全部由
 * {@link AgentTriggerService} 与 ai-service 共同保证。</p>
 */
@RestController
@RequestMapping("/api/internal/agent")
public class InternalAgentTriggerController {

    private final AgentTriggerService service;

    public InternalAgentTriggerController(AgentTriggerService service) {
        this.service = service;
    }

    @PostMapping("/trigger")
    public ApiResponse<Map<String, Object>> trigger(@RequestBody JsonNode body) {
        JsonNode alertId = body == null ? null : body.get("alertId");
        if (alertId == null || !alertId.canConvertToLong()) {
            throw new BusinessException(400, "alertId 必须为整数");
        }
        return ApiResponse.success(service.trigger(alertId.asLong()));
    }
}
