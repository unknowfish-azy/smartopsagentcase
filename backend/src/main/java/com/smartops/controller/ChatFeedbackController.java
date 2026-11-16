package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.CurrentUser;
import com.smartops.service.ChatFeedbackService;
import com.smartops.service.KnowledgeCandidateService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** 聊天消息反馈与全员只读共享知识。所有入口沿用登录态，无匿名访问。 */
@RestController
@RequestMapping("/api/chat-feedback")
public class ChatFeedbackController {
    private final ChatFeedbackService service;
    private final KnowledgeCandidateService candidates;

    public ChatFeedbackController(ChatFeedbackService service, KnowledgeCandidateService candidates) {
        this.service = service;
        this.candidates = candidates;
    }

    /** 提交反馈 → Agent 真独立复核 → 生成 PENDING_REVIEW 候选，返回最终复核状态。 */
    @PostMapping
    public ApiResponse<ChatFeedbackService.Feedback> create(@CurrentUser Long userId,
                                                            @RequestBody ChatFeedbackService.FeedbackRequest request) {
        return ApiResponse.success(service.create(userId, request));
    }

    /** 按消息查复核状态，前端据此在消息下方显示「复核中/已确认有误/无法确认/原答案正确」。 */
    @GetMapping
    public ApiResponse<ChatFeedbackService.Feedback> byMessage(@CurrentUser Long userId,
                                                               @RequestParam String messageId) {
        return ApiResponse.success(service.findByMessage(userId, messageId));
    }

    @GetMapping("/mine")
    public ApiResponse<List<ChatFeedbackService.Feedback>> mine(@CurrentUser Long userId,
                                                                @RequestParam(defaultValue = "20") int limit) {
        return ApiResponse.success(service.listMine(userId, limit));
    }

    /** 全员只读：仅审核 promote 后的共享条目；未审核内容不会出现在这里。 */
    @GetMapping("/shared")
    public ApiResponse<List<KnowledgeCandidateService.SharedKnowledge>> shared(@RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(candidates.listShared(limit));
    }

    /** 复核失败后允许手动重试一次（真调用，不静默重试）。 */
    @PostMapping("/{id}/retry")
    public ApiResponse<ChatFeedbackService.Feedback> retry(@CurrentUser Long userId,
                                                           @org.springframework.web.bind.annotation.PathVariable long id) {
        return ApiResponse.success(service.independentReview(userId, id));
    }
}
