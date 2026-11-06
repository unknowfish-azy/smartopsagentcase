package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.exception.BusinessException;
import com.smartops.security.RunTokenService;
import com.smartops.security.SessionUser;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 为已认证会话签发聊天 run 令牌（SEC-01/SEC-02）。
 *
 * <p>浏览器不再直连一个匿名 ai-service：先经 Java 会话拿到短时令牌，
 * 再由 ai-service 校验签名、过期与 run_id 归属。使用 GET 是因为浏览器端
 * SSE 客户端不走 axios 的 CSRF 头，且该端点不改变服务端状态。</p>
 */
@RestController
@RequestMapping("/api/chat")
public class ChatRunTokenController {

    private final RunTokenService tokens;

    public ChatRunTokenController(RunTokenService tokens) {
        this.tokens = tokens;
    }

    @GetMapping("/run-token")
    public ResponseEntity<ApiResponse<?>> issue(@AuthenticationPrincipal SessionUser actor) {
        if (actor == null || actor.id() == null) {
            throw new BusinessException(401, "请先登录");
        }
        RunTokenService.Issued issued = tokens.issue(actor.id());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(ApiResponse.success(Map.of(
                        "runToken", issued.token(),
                        "runId", issued.runId(),
                        "expiresInSeconds", issued.ttlSeconds()
                )));
    }
}
