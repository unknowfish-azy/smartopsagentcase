package com.smartops.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Collections;
import java.util.Enumeration;

public class TrustedUserIdFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException, IOException {
        var authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication != null && authentication.getPrincipal() instanceof SessionUser user) {
            chain.doFilter(new HttpServletRequestWrapper(request) {
                @Override public String getHeader(String name) {
                    return "X-User-Id".equalsIgnoreCase(name) ? user.id().toString() : super.getHeader(name);
                }
                @Override public Enumeration<String> getHeaders(String name) {
                    return "X-User-Id".equalsIgnoreCase(name) ? Collections.enumeration(Collections.singleton(user.id().toString())) : super.getHeaders(name);
                }
            }, response);
        } else chain.doFilter(request, response);
    }
}
