package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.service.OperatorMemoryService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 对话记忆闭环内部接口（ai-service 调用）。
 *
 * <p>只接受 {@code X-SmartOps-Internal-Token}：聊天请求由浏览器直连 ai-service，
 * 浏览器会话不能代替这个身份。用户归属由 ai-service 从 Java 签发的 run 令牌
 * subject 里取，不接受客户端自报的 userId。</p>
 */
@RestController
@RequestMapping("/api/internal/memory")
public class InternalMemoryController {

    private final OperatorMemoryService service;

    public InternalMemoryController(OperatorMemoryService service) {
        this.service = service;
    }

    /** 聊天前置召回：用户这句话里包含哪条已沉淀的记忆。 */
    @PostMapping("/recall")
    public ApiResponse<List<OperatorMemoryService.Memory>> recall(@RequestBody RecallRequest request) {
        if (request == null || request.userId() == null) return ApiResponse.success(List.of());
        return ApiResponse.success(service.recall(request.userId(), request.query(), request.limit()));
    }

    /** 聊天后回写：用户明确教给的规则（「以后遇到 X 先 Y」）。 */
    @PostMapping("/remember")
    public ApiResponse<OperatorMemoryService.Memory> remember(@RequestBody RememberRequest request) {
        if (request == null || request.userId() == null) return ApiResponse.success(null);
        return ApiResponse.success(service.recordChatPreference(
                request.userId(), request.incidentKey(), request.preferredAction(), request.sourceRefs()));
    }

    /** Agent 运行失败后的复盘沉淀：教训写入 DECISION_LOOP 记忆，供下次 recall 注入。 */
    @PostMapping("/experience")
    public ApiResponse<OperatorMemoryService.Memory> experience(@RequestBody ExperienceRequest request) {
        if (request == null || request.userId() == null) return ApiResponse.success(null);
        return ApiResponse.success(service.recordLearned(
                request.userId(), request.incidentKey(), request.preferredAction(), request.sourceRefs()));
    }

    public record RecallRequest(Long userId, String query, int limit) {}

    public record RememberRequest(Long userId, String incidentKey, String preferredAction, String sourceRefs) {}

    public record ExperienceRequest(Long userId, String incidentKey, String preferredAction, String sourceRefs) {}
}
