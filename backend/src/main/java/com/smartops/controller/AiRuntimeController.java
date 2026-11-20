package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.runtime.LocalAiRuntimeService;
import com.smartops.security.SessionUser;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.Set;

/**
 * 本地 AI 能力链启停入口。
 *
 * <p>状态读取对所有登录用户开放（普通用户只看到状态灯），启停只允许 ADMIN，
 * 且必须来自本机回环地址；能力本身由 {@code smartops.runtime.control.enabled}
 * 控制，默认关闭，仅 local profile 打开。
 */
@RestController
@RequestMapping("/api/runtime/ai")
public class AiRuntimeController {

    private static final Set<String> LOOPBACK = Set.of("127.0.0.1", "0:0:0:0:0:0:0:1", "::1");

    private final LocalAiRuntimeService runtime;

    public AiRuntimeController(LocalAiRuntimeService runtime) {
        this.runtime = runtime;
    }

    @GetMapping("/status")
    public ApiResponse<Map<String, Object>> status(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(runtime.status(actor != null && "admin".equals(actor.role())));
    }

    @PostMapping("/start")
    public ResponseEntity<ApiResponse<Map<String, Object>>> start(@AuthenticationPrincipal SessionUser actor,
                                                                  HttpServletRequest request) {
        return trigger(actor, request, true);
    }

    @PostMapping("/stop")
    public ResponseEntity<ApiResponse<Map<String, Object>>> stop(@AuthenticationPrincipal SessionUser actor,
                                                                 HttpServletRequest request) {
        return trigger(actor, request, false);
    }

    private ResponseEntity<ApiResponse<Map<String, Object>>> trigger(SessionUser actor, HttpServletRequest request,
                                                                     boolean start) {
        if (!LOOPBACK.contains(request.getRemoteAddr())) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(ApiResponse.error(403, "仅允许在本机操作本地运行时"));
        }
        try {
            Map<String, Object> result = start ? runtime.start(actor) : runtime.stop(actor);
            return ResponseEntity.ok(ApiResponse.success(result));
        } catch (IllegalStateException conflict) {
            return ResponseEntity.status(HttpStatus.CONFLICT)
                    .body(ApiResponse.error(409, conflict.getMessage()));
        }
    }
}
