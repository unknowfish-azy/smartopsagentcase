package com.smartops.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@Component
public class InternalTokenAuthenticationFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-SmartOps-Internal-Token";

    /** 仅令牌校验通过才写入；供内部只读通道区分"真的内部调用"与开发绕过。 */
    public static final String VALIDATED_ATTRIBUTE = "smartops.internal-token-validated";

    private final String expectedToken;
    private final boolean developmentBypass;

    public InternalTokenAuthenticationFilter(
            @Value("${smartops.security.internal-token:}") String expectedToken,
            @Value("${smartops.security.internal-bypass:false}") boolean developmentBypass
    ) {
        this.expectedToken = expectedToken;
        this.developmentBypass = developmentBypass;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        boolean runtime = path.matches("/api/model-connections/[^/]+/(runtime|invoke)");
        boolean inspectorWrite = "POST".equalsIgnoreCase(request.getMethod())
                && (path.equals("/api/inspector/check")
                || path.equals("/api/inspector/verify")
                || path.equals("/api/inspector/replan"));
        // 恢复契约、对话记忆与 Agent 账本写入只允许 agent / ai-service 侧调用，浏览器会话不得代替内部身份。
        boolean internalWrite = path.startsWith("/api/internal/recovery/")
                || path.startsWith("/api/internal/memory/")
                || path.startsWith("/api/internal/agent-ledger/")
                || path.equals("/api/internal/agent/trigger");
        // W7：系统触发的只读初诊没有浏览器会话，只允许内部令牌读取告警面（GET，精确路径）。
        boolean internalRead = "GET".equalsIgnoreCase(request.getMethod())
                && path.equals("/api/sentinel/alerts");
        // CRUD endpoints are called by the web application. Only runtime and
        // invoke remain internal tool boundaries.
        return !runtime && !inspectorWrite && !internalWrite && !internalRead;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        if (developmentBypass) {
            filterChain.doFilter(request, response);
            return;
        }

        if (expectedToken == null || expectedToken.isBlank()) {
            reject(response, HttpServletResponse.SC_SERVICE_UNAVAILABLE,
                    "Internal authentication is not configured");
            return;
        }

        String suppliedToken = request.getHeader(HEADER);
        if (suppliedToken == null || suppliedToken.isBlank()) {
            reject(response, HttpServletResponse.SC_UNAUTHORIZED,
                    "Internal authentication is required");
            return;
        }

        if (!MessageDigest.isEqual(
                expectedToken.getBytes(StandardCharsets.UTF_8),
                suppliedToken.getBytes(StandardCharsets.UTF_8)
        )) {
            reject(response, HttpServletResponse.SC_FORBIDDEN,
                    "Internal authentication failed");
            return;
        }

        request.setAttribute(VALIDATED_ATTRIBUTE, Boolean.TRUE);
        filterChain.doFilter(request, response);
    }

    private void reject(HttpServletResponse response, int status, String message)
            throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(
                "{\"code\":" + status + ",\"message\":\"" + message + "\"}"
        );
    }
}
