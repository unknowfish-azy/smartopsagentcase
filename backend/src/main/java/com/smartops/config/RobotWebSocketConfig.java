package com.smartops.config;

import com.smartops.robot.RobotBridgeWebSocketHandler;
import com.smartops.robot.RobotConsoleWebSocketHandler;
import com.smartops.security.AuthenticatedSessionHandshakeInterceptor;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * 巡检机器人 WebSocket 端点。
 *
 * <p>两条通道职责分离：
 * <ul>
 *   <li>{@code /ws/robot/console}：前端控制台，走会话鉴权；</li>
 *   <li>{@code /ws/robot/bridge}：蓝牙桥，走独立内部 token（在 handler 内校验，fail-closed）。</li>
 * </ul>
 * 桥端点不挂会话拦截器（桥是无头进程，没有用户会话）。</p>
 */
@Configuration
@EnableWebSocket
@RequiredArgsConstructor
public class RobotWebSocketConfig implements WebSocketConfigurer {

    private final RobotConsoleWebSocketHandler consoleHandler;
    private final RobotBridgeWebSocketHandler bridgeHandler;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(consoleHandler, "/ws/robot/console")
                .addInterceptors(new AuthenticatedSessionHandshakeInterceptor())
                .setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
        registry.addHandler(bridgeHandler, "/ws/robot/bridge")
                .setAllowedOriginPatterns("*");
    }
}
