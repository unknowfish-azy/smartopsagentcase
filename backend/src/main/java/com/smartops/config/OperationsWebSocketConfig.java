package com.smartops.config;

import com.smartops.operations.OperationsTerminalWebSocketHandler;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import com.smartops.security.AuthenticatedSessionHandshakeInterceptor;

@Configuration
@EnableWebSocket
@RequiredArgsConstructor
public class OperationsWebSocketConfig implements WebSocketConfigurer {
    private final OperationsTerminalWebSocketHandler handler;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/operations/terminal")
                .addInterceptors(new AuthenticatedSessionHandshakeInterceptor())
                .setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
    }
}
