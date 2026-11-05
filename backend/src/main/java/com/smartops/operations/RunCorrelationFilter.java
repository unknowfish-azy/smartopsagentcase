package com.smartops.operations;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

/** Correlation boundary for run-event schema 1.0.0; never records request payloads. */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RunCorrelationFilter extends OncePerRequestFilter {
    private static final Pattern ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}");
    private static String safeId(String value) {
        return value != null && ID.matcher(value).matches() ? value : UUID.randomUUID().toString().replace("-", "");
    }
    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String requestId = safeId(request.getHeader("X-Request-ID"));
        String suppliedTaskId = request.getHeader("X-Task-ID");
        String taskId = suppliedTaskId == null ? requestId : safeId(suppliedTaskId);
        String runId = safeId(request.getHeader("X-Run-ID"));
        // This filter owns the request MDC scope: only validated correlation IDs enter it.
        MDC.clear();
        try {
            bind(request, response, "request_id", "X-Request-ID", requestId);
            bind(request, response, "task_id", "X-Task-ID", taskId);
            bind(request, response, "run_id", "X-Run-ID", runId);
            request.setAttribute("run_event_schema_version", "1.0.0");
            chain.doFilter(request, response);
        } finally {
            MDC.clear();
        }
    }
    private static void bind(HttpServletRequest request, HttpServletResponse response, String attribute, String header, String value) {
        request.setAttribute(attribute, value);
        response.setHeader(header, value);
        MDC.put(attribute, value);
    }
}
