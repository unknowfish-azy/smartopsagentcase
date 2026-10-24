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
        // CRUD endpoints are called by the web application. Only runtime and
        // invoke remain internal tool boundaries.
        return !runtime && !inspectorWrite;
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
