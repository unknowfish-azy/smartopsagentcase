package com.smartops.robot;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.service.RobotControlService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 机器人控制台端点（{@code /ws/robot/console}）：人工态遥控通道。
 *
 * <p>链路：前端摇杆 → 本端点 → {@link RobotControlService}（白名单+钳位+限流+审计）
 * → 桥 → 设备。**整条链路零模型调用**，保证遥控延迟可控。
 * 鉴权复用会话握手拦截器，操作人取自会话用户，不接受消息体自报身份。</p>
 */
@Component
@RequiredArgsConstructor
public class RobotConsoleWebSocketHandler extends TextWebSocketHandler {

    private final ObjectMapper mapper;
    private final RobotTelemetryHub hub;
    private final RobotControlService control;
    private final UserAccountService accounts;

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws IOException {
        if (!(session.getPrincipal() instanceof SessionUser)) {
            session.close(CloseStatus.POLICY_VIOLATION);
            return;
        }
        hub.attachConsole(session);
        send(session, "hello", Map.of("capabilities", java.util.List.of("MOVE", "PTZ", "SPEAK", "CAPTURE", "STOP")));
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        hub.detachConsole(session);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        if (!(session.getPrincipal() instanceof SessionUser user)) {
            try {
                session.close(CloseStatus.POLICY_VIOLATION);
            } catch (IOException ignored) {
                // 会话已失效
            }
            return;
        }
        JsonNode root;
        try {
            root = mapper.readTree(message.getPayload());
        } catch (Exception e) {
            sendError(session, "ROBOT_INVALID_MESSAGE", "消息不是合法 JSON");
            return;
        }
        String type = root.path("type").asText("");
        JsonNode payload = root.path("payload");
        String deviceKey = payload.path("deviceKey").asText("");

        try {
            switch (type) {
                case "cmd" -> {
                    if (!configurator(user, session)) {
                        return;
                    }
                    @SuppressWarnings("unchecked")
                    Map<String, Object> params = payload.has("params")
                            ? mapper.convertValue(payload.get("params"), Map.class)
                            : Map.of();
                    Map<String, Object> result = control.command(deviceKey, "CONSOLE",
                            payload.path("op").asText(""), params, user.username());
                    send(session, "cmd_result", result);
                }
                case "mode" -> {
                    if (!configurator(user, session)) {
                        return;
                    }
                    RobotMode target = RobotMode.valueOf(payload.path("mode").asText("").toUpperCase());
                    send(session, "mode_result", control.switchMode(deviceKey, target, user.username()));
                }
                // 急停对任何登录用户开放（与 POST /estop 口径一致）：安全动作不允许因权限拒绝而延迟
                case "estop" -> send(session, "estop_result", control.emergencyStop(deviceKey, user.username()));
                case "reset" -> {
                    if (!configurator(user, session)) {
                        return;
                    }
                    send(session, "reset_result", control.reset(deviceKey, user.username()));
                }
                // M1 全量广播：控制台无需按设备订阅，subscribe 仅作协议向前兼容
                case "subscribe" -> { }
                default -> sendError(session, "ROBOT_UNSUPPORTED_MESSAGE", "不支持的指令类型：" + type);
            }
        } catch (RobotCommandPolicy.RobotPolicyViolation violation) {
            sendError(session, violation.code(), violation.getMessage());
        } catch (BusinessException e) {
            sendError(session, "ROBOT_REJECTED", e.getMessage());
        } catch (IllegalArgumentException e) {
            sendError(session, "ROBOT_INVALID_MODE", "未知运行态");
        } catch (RuntimeException e) {
            sendError(session, "ROBOT_ERROR", "指令处理失败");
        }
    }

    /**
     * 写操作门禁：与 HTTP 侧 {@code requireConfigurator} 同口径（admin.config）。
     * 摇杆遥测通道同样受控，否则普通账号可绕过 REST 直接驱动设备。
     */
    private boolean configurator(SessionUser user, WebSocketSession session) {
        if (accounts.hasPlatformCapability(user, "admin.config")) {
            return true;
        }
        sendError(session, "ROBOT_FORBIDDEN", "需要 admin.config 能力");
        return false;
    }

    private void send(WebSocketSession session, String type, Map<String, Object> payload) {
        if (!session.isOpen()) {
            return;
        }
        try {
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("type", type);
            envelope.put("ts", System.currentTimeMillis());
            envelope.put("payload", payload);
            synchronized (session) {
                session.sendMessage(new TextMessage(mapper.writeValueAsString(envelope)));
            }
        } catch (IOException | IllegalStateException ignored) {
            // 控制台连接已断开，不做补偿
        }
    }

    private void sendError(WebSocketSession session, String code, String message) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("code", code);
        payload.put("message", message);
        send(session, "error", payload);
    }
}
