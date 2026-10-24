package com.smartops.operations;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.context.event.EventListener;
import org.springframework.security.web.session.HttpSessionDestroyedEvent;
import org.springframework.security.web.session.HttpSessionIdChangedEvent;
import org.springframework.web.socket.server.support.HttpSessionHandshakeInterceptor;
import com.smartops.security.AuthenticatedSessionHandshakeInterceptor;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.security.AdminMfaService;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
@RequiredArgsConstructor
public class OperationsTerminalWebSocketHandler extends TextWebSocketHandler {
    private final OperationRuntimeRegistry registry;
    private final ObjectMapper objectMapper;
    private final UserAccountService accounts;
    private final AdminMfaService mfa;
    private final Map<String, String> sessionRuntimes = new ConcurrentHashMap<>();
    private final Map<String, WebSocketSession> sockets = new ConcurrentHashMap<>();

    @Override public void afterConnectionEstablished(WebSocketSession socket) throws IOException {
        sockets.put(socket.getId(), socket);
        if (!hasValidSession(socket)) {
            sockets.remove(socket.getId());
            socket.close(CloseStatus.POLICY_VIOLATION);
        }
    }

    @EventListener public void onSessionDestroyed(HttpSessionDestroyedEvent event) {
        try { event.getSession().setAttribute(AuthenticatedSessionHandshakeInterceptor.REVOKED, true); } catch (IllegalStateException ignored) { }
        closeSessionSockets(event.getId());
    }

    @EventListener public void onSessionIdChanged(HttpSessionIdChangedEvent event) {
        closeSessionSockets(event.getOldSessionId());
    }

    private void closeSessionSockets(String sessionId) {
        for (WebSocketSession socket : sockets.values()) {
            if (sessionId.equals(socket.getAttributes().get(HttpSessionHandshakeInterceptor.HTTP_SESSION_ID_ATTR_NAME))) {
                sockets.remove(socket.getId());
                try { socket.close(CloseStatus.POLICY_VIOLATION); } catch (IOException ignored) { }
            }
        }
    }

    private boolean hasValidSession(WebSocketSession socket) {
        if (!(socket.getAttributes().get(AuthenticatedSessionHandshakeInterceptor.HTTP_SESSION) instanceof HttpSession session)) return false;
        try {
            if (!session.getId().equals(socket.getAttributes().get(HttpSessionHandshakeInterceptor.HTTP_SESSION_ID_ATTR_NAME))
                    || Boolean.TRUE.equals(session.getAttribute(AuthenticatedSessionHandshakeInterceptor.REVOKED))) return false;
            if (!(session.getAttribute(HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY) instanceof SecurityContext context)
                    || context.getAuthentication() == null || !context.getAuthentication().isAuthenticated()
                    || !(context.getAuthentication().getPrincipal() instanceof SessionUser user)) return false;
            return !user.mustChangePassword() && accounts.isCurrent(user) && mfa.validSession(user, session) && user.id().equals(userId(socket));
        } catch (IllegalStateException | com.smartops.exception.BusinessException invalidated) { return false; }
    }

    @Override
    public void handleTextMessage(WebSocketSession socket, TextMessage message) throws IOException {
        if (!sockets.containsKey(socket.getId()) || !hasValidSession(socket)) {
            sockets.remove(socket.getId());
            socket.close(CloseStatus.POLICY_VIOLATION);
            return;
        }
        TerminalMessage command;
        try {
            command = objectMapper.readValue(message.getPayload(), TerminalMessage.class);
        } catch (Exception ex) {
            send(socket, "ERROR", null, "INVALID_MESSAGE");
            return;
        }
        Long userId = userId(socket);
        try {
            switch (command.type() == null ? "" : command.type().toUpperCase()) {
                case "OPEN" -> open(socket, userId, command.runtimeId());
                case "INPUT" -> registry.requireOwned(runtime(socket, command), userId).write(command.data() == null ? "" : command.data());
                case "RESIZE" -> registry.requireOwned(runtime(socket, command), userId).resize(command.columns() == null ? 80 : command.columns(), command.rows() == null ? 24 : command.rows());
                case "CLOSE" -> closeRuntime(socket, userId);
                default -> send(socket, "ERROR", null, "UNSUPPORTED_MESSAGE");
            }
        } catch (RuntimeException | IOException ex) {
            send(socket, "ERROR", null, OperationRedactor.redact(ex.getMessage()));
        }
    }

    private void open(WebSocketSession socket, Long userId, String runtimeId) throws IOException {
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        sessionRuntimes.put(socket.getId(), runtimeId);
        runtime.onOutput(new OperationRuntime.OutputListener() {
            @Override public void onOutput(String output) { sendQuietly(socket, "OUTPUT", runtimeId, output); }
            @Override public void onClosed(Integer exitCode) { sendQuietly(socket, "EXIT", runtimeId, exitCode == null ? "" : String.valueOf(exitCode)); }
        });
        send(socket, "STATUS", runtimeId, "ONLINE");
    }

    private String runtime(WebSocketSession socket, TerminalMessage command) {
        String selected = command.runtimeId() == null ? sessionRuntimes.get(socket.getId()) : command.runtimeId();
        if (selected == null) throw new com.smartops.exception.BusinessException(409, "TERMINAL_NOT_OPEN");
        return selected;
    }

    private void closeRuntime(WebSocketSession socket, Long userId) {
        String runtimeId = sessionRuntimes.remove(socket.getId());
        if (runtimeId != null) registry.removeOwned(runtimeId, userId).close();
    }

    @Override public void afterConnectionClosed(WebSocketSession socket, CloseStatus status) {
        sockets.remove(socket.getId());
        String runtimeId = sessionRuntimes.remove(socket.getId());
        if (runtimeId != null) {
            try { registry.removeOwned(runtimeId, userId(socket)).close(); } catch (RuntimeException ignored) { }
        }
    }

    private Long userId(WebSocketSession socket) {
        if (socket.getPrincipal() instanceof org.springframework.security.core.Authentication authentication
                && authentication.getPrincipal() instanceof com.smartops.security.SessionUser user) return user.id();
        throw new com.smartops.exception.BusinessException(401, "请先登录");
    }

    private void send(WebSocketSession socket, String type, String runtimeId, String data) throws IOException {
        if (socket.isOpen()) socket.sendMessage(new TextMessage(objectMapper.writeValueAsString(Map.of("type", type, "runtimeId", runtimeId == null ? "" : runtimeId, "data", data == null ? "" : data))));
    }

    private void sendQuietly(WebSocketSession socket, String type, String runtimeId, String data) {
        try { send(socket, type, runtimeId, data); } catch (IOException ignored) { }
    }
}
