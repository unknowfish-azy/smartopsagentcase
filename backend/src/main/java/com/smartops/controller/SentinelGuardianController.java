package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import com.smartops.sentinel.SentinelGuardianService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 哨兵守护 Agent 接口：自动取证结果、指标基线学习与阈值建议确认。
 */
@RestController
@RequestMapping("/api/sentinel/guardian")
@RequiredArgsConstructor
public class SentinelGuardianController {

    private final SentinelGuardianService guardian;

    @GetMapping("/profiles")
    public ApiResponse<?> profiles(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(guardian.listProfiles(userId(actor)));
    }

    @GetMapping("/evidence")
    public ApiResponse<?> evidence(@AuthenticationPrincipal SessionUser actor,
                                   @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(guardian.listEvidence(userId(actor), limit));
    }

    @GetMapping("/stats")
    public ApiResponse<?> stats(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(guardian.stats(userId(actor)));
    }

    @PostMapping("/learn")
    public ApiResponse<?> learn(@AuthenticationPrincipal SessionUser actor) {
        userId(actor);
        return ApiResponse.success(Map.of("learned", guardian.learnAll()));
    }

    @PostMapping("/profiles/{id}/apply")
    public ApiResponse<?> apply(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        return ApiResponse.success(guardian.apply(userId(actor), id));
    }

    @PostMapping("/profiles/{id}/dismiss")
    public ApiResponse<?> dismiss(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        guardian.dismiss(userId(actor), id);
        return ApiResponse.success(null);
    }

    @PostMapping("/alerts/{alertId}/collect")
    public ApiResponse<?> collect(@AuthenticationPrincipal SessionUser actor, @PathVariable long alertId) {
        return ApiResponse.success(guardian.collect(userId(actor), alertId));
    }

    private long userId(SessionUser actor) {
        if (actor == null || actor.id() == null) {
            throw new com.smartops.exception.BusinessException(401, "需要登录后使用守护 Agent");
        }
        return actor.id();
    }
}
