package com.smartops.robot;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 机器人与桥的连接hub：唯一路由器。
 *
 * <p>前端不直连桥，桥不感知前端；所有消息经本类转发。
 * 遥测只保留内存最新快照（不入库，避免高频写盘），
 * 关键状态变化（E-STOP/FAULT）由 {@code RobotControlService} 落审计表。</p>
 *
 * <p>线程安全：桥连接、控制台连接与遥测快照均为并发容器；
 * 广播对单个会话发送失败时静默摘除，不阻塞其他订阅者。</p>
 */
@Component
@RequiredArgsConstructor
public class RobotTelemetryHub {

    private final ObjectMapper mapper;

    /** deviceKey → 桥侧 WebSocket 会话（M1 单桥可承载多设备，故按设备维度索引）。 */
    private final Map<String, WebSocketSession> bridges = new ConcurrentHashMap<>();
    /** 控制台侧会话（接收所有已订阅设备的遥测与事件）。 */
    private final Map<String, WebSocketSession> consoles = new ConcurrentHashMap<>();
    /** deviceKey → 最新遥测快照。 */
    private final Map<String, Map<String, Object>> latest = new ConcurrentHashMap<>();
    /** deviceKey → 最近一次收到遥测的时间戳（毫秒），用于心跳超时判定。 */
    private final Map<String, Long> lastSeen = new ConcurrentHashMap<>();

    public void attachBridge(String deviceKey, WebSocketSession session) {
        WebSocketSession previous = bridges.put(deviceKey, session);
        if (previous != null && previous != session && previous.isOpen()) {
            try {
                previous.close();
            } catch (IOException ignored) {
                // 旧连接已失效，无需处理
            }
        }
    }

    public void detachBridge(String deviceKey, WebSocketSession session) {
        bridges.remove(deviceKey, session);
        lastSeen.remove(deviceKey);
    }

    public void attachConsole(WebSocketSession session) {
        consoles.put(session.getId(), session);
    }

    public void detachConsole(WebSocketSession session) {
        consoles.remove(session.getId());
    }

    /** 是否已有桥承载该设备。 */
    public boolean bridgeConnected(String deviceKey) {
        WebSocketSession session = bridges.get(deviceKey);
        return session != null && session.isOpen();
    }

    /** 当前已连接的桥数量（用于机队自检）。 */
    public int bridgeCount() {
        return (int) bridges.values().stream().filter(WebSocketSession::isOpen).count();
    }

    /**
     * 下行命令到桥：信封 {@code {type, ts, payload}}。
     *
     * @return true 表示已投递到桥连接；false 表示桥未连接（调用方负责落 FAULT/提示）
     */
    public boolean sendToBridge(String deviceKey, String type, Map<String, Object> payload) {
        WebSocketSession session = bridges.get(deviceKey);
        if (session == null || !session.isOpen()) {
            return false;
        }
        return sendQuietly(session, type, payload);
    }

    /** 桥上报遥测：更新快照并广播给控制台。 */
    public void onTelemetry(String deviceKey, Map<String, Object> payload) {
        Map<String, Object> snapshot = new LinkedHashMap<>(payload);
        snapshot.put("deviceKey", deviceKey);
        snapshot.put("receivedAt", Instant.now().toString());
        latest.put(deviceKey, snapshot);
        lastSeen.put(deviceKey, System.currentTimeMillis());
        broadcast("telemetry", snapshot);
    }

    /** 桥上报事件（障碍停止/到达/故障等）：仅广播，不落库（由控制服务按需落审计）。 */
    public void onDeviceEvent(String deviceKey, Map<String, Object> payload) {
        Map<String, Object> event = new LinkedHashMap<>(payload);
        event.put("deviceKey", deviceKey);
        event.put("ts", Instant.now().toString());
        broadcast("device_event", event);
    }

    /** 桥上报关键帧（低频）：仅广播给控制台，不落盘原始图像。 */
    public void onFrame(String deviceKey, Map<String, Object> payload) {
        Map<String, Object> frame = new LinkedHashMap<>(payload);
        frame.put("deviceKey", deviceKey);
        frame.put("ts", Instant.now().toString());
        broadcast("frame", frame);
    }

    /** 广播任意类型消息给所有控制台会话。 */
    public void broadcast(String type, Map<String, Object> payload) {
        if (consoles.isEmpty()) {
            return;
        }
        for (WebSocketSession session : new ArrayList<>(consoles.values())) {
            if (!sendQuietly(session, type, payload)) {
                consoles.remove(session.getId());
            }
        }
    }

    /** 单设备遥测快照；无数据返回 null（不伪造默认值）。 */
    public Map<String, Object> telemetry(String deviceKey) {
        return latest.get(deviceKey);
    }

    /** 全部设备遥测快照（只读副本）。 */
    public Map<String, Object> allTelemetry() {
        return new LinkedHashMap<>(latest);
    }

    /** 距上次收到遥测的毫秒数；从未收到返回 {@link Long#MAX_VALUE}。 */
    public long silenceMillis(String deviceKey) {
        Long seen = lastSeen.get(deviceKey);
        return seen == null ? Long.MAX_VALUE : System.currentTimeMillis() - seen;
    }

    /** 已建立桥连接的设备键列表。 */
    public List<String> connectedDeviceKeys() {
        List<String> keys = new ArrayList<>();
        bridges.forEach((key, session) -> {
            if (session.isOpen()) {
                keys.add(key);
            }
        });
        return keys;
    }

    private boolean sendQuietly(WebSocketSession session, String type, Map<String, Object> payload) {
        if (!session.isOpen()) {
            return false;
        }
        try {
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("type", type);
            envelope.put("ts", Instant.now().toEpochMilli());
            envelope.put("payload", payload);
            synchronized (session) {
                session.sendMessage(new TextMessage(mapper.writeValueAsString(envelope)));
            }
            return true;
        } catch (IOException | IllegalStateException e) {
            return false;
        }
    }
}
