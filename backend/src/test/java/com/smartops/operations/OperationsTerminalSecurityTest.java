package com.smartops.operations;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.session.HttpSessionDestroyedEvent;
import org.springframework.security.web.session.HttpSessionIdChangedEvent;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.server.support.HttpSessionHandshakeInterceptor;
import com.smartops.security.SessionUser;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextImpl;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

import java.util.Map;
import java.util.List;

import static org.mockito.Mockito.*;

class OperationsTerminalSecurityTest {
    private final com.smartops.security.AdminMfaService mfa = mock(com.smartops.security.AdminMfaService.class);
    @org.junit.jupiter.api.BeforeEach void mfaCurrent() { when(mfa.validSession(any(), any())).thenReturn(true); }

    @Test void mfaVersionChangeStopsCommandsBeforeSessionRevocationEventArrives() throws Exception {
        var registry = mock(OperationRuntimeRegistry.class);
        var handler = new OperationsTerminalWebSocketHandler(registry, new ObjectMapper(), accounts(), mfa);
        var socket = socket("mfa-version", new MockHttpSession());
        handler.afterConnectionEstablished(socket);
        when(mfa.validSession(any(), any())).thenReturn(false);
        handler.handleTextMessage(socket, new TextMessage("{\"type\":\"OPEN\",\"runtimeId\":\"owned-runtime\"}"));
        verifyNoInteractions(registry);
        verify(socket).close(CloseStatus.POLICY_VIOLATION);
    }

    private com.smartops.security.UserAccountService accounts() {
        var accounts = mock(com.smartops.security.UserAccountService.class);
        when(accounts.isCurrent(any())).thenReturn(true);
        return accounts;
    }

    @Test void revokedAccountVersionCannotUseAnOtherwiseLiveSocket() throws Exception {
        var registry = mock(OperationRuntimeRegistry.class);
        var accounts = accounts();
        var handler = new OperationsTerminalWebSocketHandler(registry, new ObjectMapper(), accounts, mfa);
        var socket = socket("revoked-account", new MockHttpSession());
        handler.afterConnectionEstablished(socket);
        when(accounts.isCurrent(any())).thenReturn(false);
        handler.handleTextMessage(socket, new TextMessage("{\"type\":\"OPEN\",\"runtimeId\":\"owned-runtime\"}"));
        verifyNoInteractions(registry);
        verify(socket).close(CloseStatus.POLICY_VIOLATION);
    }
    private WebSocketSession socket(String id, MockHttpSession session) {
        var socket = mock(WebSocketSession.class);
        var auth = UsernamePasswordAuthenticationToken.authenticated(new SessionUser(1L, "admin", "admin"), null, List.of());
        session.setAttribute(HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY, new SecurityContextImpl(auth));
        when(socket.getId()).thenReturn(id);
        when(socket.getPrincipal()).thenReturn(auth);
        when(socket.getAttributes()).thenReturn(Map.of(HttpSessionHandshakeInterceptor.HTTP_SESSION_ID_ATTR_NAME, session.getId(), "SMARTOPS_HTTP_SESSION", session));
        return socket;
    }

    @Test void destroyedBeforeRegistrationCannotAccessRuntime() throws Exception {
        var registry = mock(OperationRuntimeRegistry.class);
        var handler = new OperationsTerminalWebSocketHandler(registry, new ObjectMapper(), accounts(), mfa);
        var session = new MockHttpSession();
        var socket = socket("late", session);
        session.invalidate();
        handler.onSessionDestroyed(new HttpSessionDestroyedEvent(session));
        handler.afterConnectionEstablished(socket);
        handler.handleTextMessage(socket, new TextMessage("{\"type\":\"OPEN\",\"runtimeId\":\"owned-runtime\"}"));
        verifyNoInteractions(registry);
        verify(socket, atLeastOnce()).close(CloseStatus.POLICY_VIOLATION);
    }

    @Test void rotatedBeforeRegistrationCannotAccessRuntime() throws Exception {
        var registry = mock(OperationRuntimeRegistry.class);
        var handler = new OperationsTerminalWebSocketHandler(registry, new ObjectMapper(), accounts(), mfa);
        var session = new MockHttpSession();
        var socket = socket("late", session);
        String previousId = session.getId();
        session.changeSessionId();
        handler.onSessionIdChanged(new HttpSessionIdChangedEvent(session, previousId));
        handler.afterConnectionEstablished(socket);
        handler.handleTextMessage(socket, new TextMessage("{\"type\":\"OPEN\",\"runtimeId\":\"owned-runtime\"}"));
        verifyNoInteractions(registry);
        verify(socket, atLeastOnce()).close(CloseStatus.POLICY_VIOLATION);
    }

    @Test void messagesRecheckSessionValidityEvenBeforeEventDelivery() throws Exception {
        var registry = mock(OperationRuntimeRegistry.class);
        var handler = new OperationsTerminalWebSocketHandler(registry, new ObjectMapper(), accounts(), mfa);
        var session = new MockHttpSession();
        var socket = socket("connected", session);
        handler.afterConnectionEstablished(socket);
        session.invalidate();
        handler.handleTextMessage(socket, new TextMessage("{\"type\":\"OPEN\",\"runtimeId\":\"owned-runtime\"}"));
        verifyNoInteractions(registry);
        verify(socket).close(CloseStatus.POLICY_VIOLATION);
    }

    @Test void rotatingTheHttpSessionClosesItsOldTerminalSockets() throws Exception {
        var handler = new OperationsTerminalWebSocketHandler(mock(OperationRuntimeRegistry.class), new ObjectMapper(), accounts(), mfa);
        var session = new MockHttpSession();
        var socket = socket("terminal", session);
        handler.afterConnectionEstablished(socket);
        String previousId = session.getId();
        session.changeSessionId();
        handler.onSessionIdChanged(new HttpSessionIdChangedEvent(session, previousId));
        verify(socket).close(CloseStatus.POLICY_VIOLATION);
    }
    @Test void logoutClosesOnlySocketsBelongingToTheDestroyedSession() throws Exception {
        var handler = new OperationsTerminalWebSocketHandler(mock(OperationRuntimeRegistry.class), new ObjectMapper(), accounts(), mfa);
        var session = new MockHttpSession();
        var owned = socket("owned", session);
        var other = socket("other", new MockHttpSession());
        handler.afterConnectionEstablished(owned);
        handler.afterConnectionEstablished(other);
        handler.onSessionDestroyed(new HttpSessionDestroyedEvent(session));
        verify(owned).close(CloseStatus.POLICY_VIOLATION);
        verify(other, never()).close(any(CloseStatus.class));
    }
}
