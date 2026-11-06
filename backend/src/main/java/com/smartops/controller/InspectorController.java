package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.dto.inspector.InspectionRecordRequest;
import com.smartops.dto.inspector.InspectionReplanRequest;
import com.smartops.dto.inspector.InspectionVerifyRequest;
import com.smartops.security.CurrentSessions;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.service.InspectorEventService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 纠察事件接口。
 *
 * <p>SEC-08：读侧按归属过滤——普通用户只能读自己的事件；
 * 全局视图仅持有 {@code admin.audit} 能力的审计管理员可用，且每次全局读留审计。
 * 写入口（check/verify/replan）同时服务内部 token 通道（系统事件，无归属用户）与登录用户。</p>
 */
@RestController
@RequestMapping("/api/inspector")
@RequiredArgsConstructor
public class InspectorController {

    private final InspectorEventService service;
    private final UserAccountService accounts;
    private final SecurityAuditService audit;

    @GetMapping("/summary")
    public ApiResponse<Map<String, Object>> summary(HttpServletRequest request) {
        ReadScope scope = readScope(request, "summary");
        return ApiResponse.success(service.summary(scope.viewerId(), scope.global()));
    }

    @GetMapping("/events")
    public ApiResponse<List<Map<String, Object>>> events(
            HttpServletRequest request,
            @RequestParam(defaultValue = "50") int limit) {
        ReadScope scope = readScope(request, "events");
        return ApiResponse.success(service.events(limit, scope.viewerId(), scope.global()));
    }

    @GetMapping("/events/{id}")
    public ApiResponse<Map<String, Object>> event(HttpServletRequest request, @PathVariable String id) {
        ReadScope scope = readScope(request, "event:" + id);
        return ApiResponse.success(service.event(id, scope.viewerId(), scope.global()));
    }

    @PostMapping("/check")
    public ApiResponse<Map<String, Object>> check(
            HttpServletRequest request,
            @Valid @RequestBody InspectionRecordRequest request2) {
        SessionUser user = CurrentSessions.optional(request);
        return ApiResponse.success(user == null
                ? service.record(request2)
                : service.record(request2, user.id()));
    }

    @PostMapping("/verify")
    public ApiResponse<Map<String, Object>> verify(
            @Valid @RequestBody InspectionVerifyRequest request) {
        return ApiResponse.success(service.verify(request));
    }

    @PostMapping("/replan")
    public ApiResponse<Map<String, Object>> replan(
            @Valid @RequestBody InspectionReplanRequest request) {
        return ApiResponse.success(service.replan(request));
    }

    @GetMapping("/statistics")
    public ApiResponse<Map<String, Object>> statistics(HttpServletRequest request) {
        ReadScope scope = readScope(request, "statistics");
        return ApiResponse.success(service.statistics(scope.viewerId(), scope.global()));
    }

    /**
     * 读侧范围判定：登录用户默认只读自己的事件；
     * 仅 {@code admin.audit} 能力持有者可看全局视图，并留审计记录。
     */
    private ReadScope readScope(HttpServletRequest request, String target) {
        SessionUser user = CurrentSessions.require(request);
        boolean global = accounts.hasPlatformCapability(user, "admin.audit");
        if (global) {
            audit.record(user, "INSPECTOR_GLOBAL_READ", target, "ALLOWED");
        }
        return new ReadScope(global ? null : user.id(), global);
    }

    private record ReadScope(Long viewerId, boolean global) { }
}
