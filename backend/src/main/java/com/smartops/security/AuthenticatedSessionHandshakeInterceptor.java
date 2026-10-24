package com.smartops.security;

import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.http.server.ServletServerHttpRequest;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.support.HttpSessionHandshakeInterceptor;

import java.util.Map;

public class AuthenticatedSessionHandshakeInterceptor extends HttpSessionHandshakeInterceptor {
    public static final String HTTP_SESSION = "SMARTOPS_HTTP_SESSION";
    public static final String REVOKED = "SMARTOPS_SESSION_REVOKED";

    public AuthenticatedSessionHandshakeInterceptor() { setCreateSession(false); }

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
            WebSocketHandler handler, Map<String, Object> attributes) throws Exception {
        if (!(request instanceof ServletServerHttpRequest servlet)) return false;
        var session = servlet.getServletRequest().getSession(false);
        if (session == null) return false;
        try {
            if (Boolean.TRUE.equals(session.getAttribute(REVOKED)) || !super.beforeHandshake(request, response, handler, attributes)) return false;
            attributes.put(HTTP_SESSION, session);
            return true;
        } catch (IllegalStateException invalidated) { return false; }
    }
}
