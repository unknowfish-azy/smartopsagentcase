package com.smartops.robot;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.service.RobotControlService;
import com.smartops.service.RobotFrameService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 蓝牙桥接入端点（{@code /ws/robot/bridge}）。
 *
 * <p>鉴权采用独立内部 token（{@code X-Robot-Bridge-Token} 握手头），与用户会话解耦；
 * 未配置 token 时一律拒连（fail-closed），与恢复契约的内部 token 口径一致。
 * 桥必须先发 {@code bridge_hello} 声明承载的 deviceKey，之后每条消息按 deviceKey 路由。</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RobotBridgeWebSocketHandler extends TextWebSocketHandler {

    public static final String TOKEN_HEADER = "X-Robot-Bridge-Token";

    private final ObjectMapper mapper;
    private final RobotTelemetryHub hub;
    private final RobotControlService control;
    private final RobotFrameService frames;

    @Value("${smartops.robot.bridge-token:}")
    private String bridgeToken;

    /** 会话级：该桥连接声明的设备键。 */
    private static final String ATTR_DEVICES = "robot.bridge.devices";

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        if (!tokenValid(session.getHandshakeHeaders().getFirst(TOKEN_HEADER))) {
            session.close(CloseStatus.POLICY_VIOLATION.withReason("ROBOT_BRIDGE_UNAUTHORIZED"));
            return;
        }
        session.getAttributes().put(ATTR_DEVICES, new ArrayList<String>());
        log.info("机器人蓝牙桥已连接：{}", session.getId());
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        List<String> devices = devicesOf(session);
        if (devices == null) {
            session.close(CloseStatus.POLICY_VIOLATION);
            return;
        }
        JsonNode root;
        try {
            root = mapper.readTree(message.getPayload());
        } catch (Exception e) {
            return; // 非法 JSON 直接忽略，不中断连接（桥侧重连成本高）
        }
        String type = root.path("type").asText("");
        JsonNode payload = root.path("payload");

        switch (type) {
            case "bridge_hello" -> {
                List<String> declared = new ArrayList<>();
                payload.path("deviceKeys").forEach(node -> {
                    String key = node.asText("").strip();
                    if (!key.isEmpty()) {
                        declared.add(key);
                    }
                });
                devices.clear();
                devices.addAll(declared);
                for (String deviceKey : declared) {
                    hub.attachBridge(deviceKey, session);
                    control.onBridgeOnline(deviceKey);
                }
                sendHelloAck(session, declared);
                log.info("机器人桥 {} 声明设备：{}", session.getId(), declared);
            }
            case "telemetry", "frame", "event" -> {
                String deviceKey = payload.path("deviceKey").asText("");
                if (!devices.contains(deviceKey)) {
                    return; // 未声明的设备一律丢弃，防止越权上报
                }
                Map<String, Object> body = mapper.convertValue(payload, Map.class);
                switch (type) {
                    case "telemetry" -> hub.onTelemetry(deviceKey, body);
                    case "frame" -> {
                        hub.onFrame(deviceKey, body);
                        frames.accept(deviceKey, body);
                    }
                    default -> hub.onDeviceEvent(deviceKey, body);
                }
            }
            case "bridge_ack" -> { /* M1 仅记录，不参与控制流 */ }
            default -> log.debug("机器人桥未知消息类型：{}", type);
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        List<String> devices = devicesOf(session);
        if (devices == null) {
            return;
        }
        for (String deviceKey : devices) {
            hub.detachBridge(deviceKey, session);
            control.onBridgeOffline(deviceKey);
        }
        log.info("机器人蓝牙桥断开：{}，设备 {}", session.getId(), devices);
    }

    /** 常量时间比较，避免 token 长度/内容被时序探测。 */
    private boolean tokenValid(String provided) {
        if (bridgeToken == null || bridgeToken.isBlank() || provided == null) {
            return false;
        }
        return MessageDigest.isEqual(
                bridgeToken.getBytes(StandardCharsets.UTF_8),
                provided.getBytes(StandardCharsets.UTF_8));
    }

    private void sendHelloAck(WebSocketSession session, List<String> devices) {
        try {
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("type", "bridge_hello_ack");
            envelope.put("ts", System.currentTimeMillis());
            envelope.put("payload", Map.of("acceptedDeviceKeys", devices));
            session.sendMessage(new TextMessage(mapper.writeValueAsString(envelope)));
        } catch (Exception e) {
            log.warn("机器人桥握手回执发送失败：{}", e.getMessage());
        }
    }

    @SuppressWarnings("unchecked")
    private List<String> devicesOf(WebSocketSession session) {
        Object value = session.getAttributes().get(ATTR_DEVICES);
        return value instanceof List ? (List<String>) value : null;
    }
}
