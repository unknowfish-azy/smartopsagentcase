package com.smartops.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Set;

public class AccountStateFilter extends OncePerRequestFilter {
    private static final Set<String> PASSWORD_FLOW = Set.of("/api/auth/session", "/api/auth/login", "/api/auth/logout", "/api/auth/password");
    private final UserAccountService accounts;
    private final AdminMfaService mfa;

    public AccountStateFilter(UserAccountService accounts, AdminMfaService mfa) { this.accounts = accounts; this.mfa = mfa; }

    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException, IOException {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof SessionUser user) {
            if (!accounts.isCurrent(user) || !mfa.validSession(user, request.getSession(false))) {
                var session = request.getSession(false);
                if (session != null) {
                    try { session.invalidate(); } catch (IllegalStateException ignored) { }
                }
                SecurityContextHolder.clearContext();
                if (!Set.of("/api/auth/session", "/api/auth/login").contains(request.getRequestURI())) {
                    reply(response, 401, "账号权限或密码已变更，请重新登录");
                    return;
                }
            } else if (user.mustChangePassword() && !PASSWORD_FLOW.contains(request.getRequestURI())) {
                reply(response, 403, "PASSWORD_CHANGE_REQUIRED：请先修改初始密码");
                return;
            }
        }
        chain.doFilter(request, response);
    }

    private void reply(HttpServletResponse response, int status, String message) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"code\":" + status + ",\"message\":\"" + message + "\"}");
    }
}
