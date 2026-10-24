package com.smartops.security;

import com.smartops.exception.BusinessException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.security.web.util.matcher.RequestMatcher;

import java.io.IOException;
import java.util.Set;

public class AdminConfirmationFilter extends OncePerRequestFilter {
    private final UserAccountService accounts;
    private final RequestMatcher administrativeRoutes;

    public AdminConfirmationFilter(UserAccountService accounts, RequestMatcher administrativeRoutes) {
        this.accounts = accounts; this.administrativeRoutes = administrativeRoutes;
    }

    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException, IOException {
        if (administrativeRoutes.matches(request) && !Set.of("GET", "HEAD", "OPTIONS").contains(request.getMethod())) {
            var authentication = SecurityContextHolder.getContext().getAuthentication();
            SessionUser actor = authentication != null && authentication.getPrincipal() instanceof SessionUser user ? user : null;
            try {
                accounts.confirmAdministration(actor, request.getHeader("X-Admin-Password"), request.getRemoteAddr());
            } catch (BusinessException rejected) {
                response.setStatus(rejected.getCode());
                response.setContentType("application/json;charset=UTF-8");
                response.getWriter().write("{\"code\":" + rejected.getCode() + ",\"message\":\"" + rejected.getMessage() + "\"}");
                return;
            }
        }
        chain.doFilter(request, response);
    }
}
