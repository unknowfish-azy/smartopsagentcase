package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.robot.RobotCommandPolicy;
import com.smartops.robot.RobotMode;
import com.smartops.robot.RobotTelemetryHub;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;

/**
 * 巡检机器人双态控制服务（M1）。
 *
 * <p>核心职责：
 * <ol>
 *   <li>状态机：AUTONOMOUS 与 HUMAN_CONTROL 互斥，非法转移 409；</li>
 *   <li>命令门禁：所有命令先过 {@link RobotCommandPolicy}，再按当前态判断是否可下发；</li>
 *   <li>审计：每条命令（含被拒）落 {@code robot_command_log}，拒绝只记规则码；</li>
 *   <li>看门狗：心跳沉默或桥断连超过阈值 → 自动 FAULT 并下发 STOP。</li>
 * </ol>
 * 急停是最高优先级旁路：不排队、不受状态机来源校验限制，但仍审计。</p>
 */
@Slf4j
@Service
public class RobotControlService {

    private final RobotRegistryService registry;
    private final RobotTelemetryHub hub;
    private final RobotFrameService frames;
    private final JdbcTemplate jdbcTemplate;
    private final long heartbeatTimeoutMs;

    /** deviceKey → 当前运行态（内存为准，变化时同步台账）。 */
    private final Map<String, RobotMode> modes = new ConcurrentHashMap<>();
    /** deviceKey → 控制锁（双态切换与命令下发互斥）。 */
    private final Map<String, ReentrantLock> locks = new ConcurrentHashMap<>();
    /** deviceKey → 最近一秒内的命令时间戳，用于限流。 */
    private final Map<String, Deque<Long>> commandWindow = new ConcurrentHashMap<>();

    public RobotControlService(RobotRegistryService registry,
            RobotTelemetryHub hub,
            RobotFrameService frames,
            JdbcTemplate jdbcTemplate,
            @Value("${smartops.robot.heartbeat-timeout-ms:600}") long heartbeatTimeoutMs) {
        this.registry = registry;
        this.hub = hub;
        this.frames = frames;
        this.jdbcTemplate = jdbcTemplate;
        this.heartbeatTimeoutMs = heartbeatTimeoutMs;
    }

    /** 当前运行态（内存快照；未接入过桥的设备为 OFFLINE）。 */
    public RobotMode modeOf(String deviceKey) {
        return modes.getOrDefault(deviceKey, RobotMode.OFFLINE);
    }

    /** 桥建立连接：OFFLINE → IDLE，并通知控制台。 */
    public void onBridgeOnline(String deviceKey) {
        locks.computeIfAbsent(deviceKey, key -> new ReentrantLock()).lock();
        try {
            RobotMode current = modeOf(deviceKey);
            if (current == RobotMode.OFFLINE) {
                apply(deviceKey, RobotMode.IDLE, "bridge", "BRIDGE_ONLINE");
            }
        } finally {
            locks.get(deviceKey).unlock();
        }
    }

    /** 桥断开：在线态一律转 FAULT（需人工复位），不静默回落 IDLE。 */
    public void onBridgeOffline(String deviceKey) {
        locks.computeIfAbsent(deviceKey, key -> new ReentrantLock()).lock();
        try {
            RobotMode current = modeOf(deviceKey);
            if (current != RobotMode.OFFLINE && current != RobotMode.E_STOP) {
                apply(deviceKey, RobotMode.FAULT, "bridge", "BRIDGE_OFFLINE");
            }
        } finally {
            locks.get(deviceKey).unlock();
        }
    }

    /**
     * 双态切换：IDLE→AUTONOMOUS / IDLE→HUMAN_CONTROL / AUTONOMOUS↔HUMAN_CONTROL 等。
     * 自主态转人工态时，进行中的任务置 PAUSED（保留 planId 供续跑）。
     */
    public Map<String, Object> switchMode(String deviceKey, RobotMode target, String operator) {
        registry.requireEnabled(deviceKey);
        ReentrantLock lock = locks.computeIfAbsent(deviceKey, key -> new ReentrantLock());
        lock.lock();
        try {
            RobotMode current = modeOf(deviceKey);
            if (current == target) {
                return modeView(deviceKey, current);
            }
            if (!current.canTransitTo(target)) {
                throw new BusinessException(409,
                        "机器人当前态 " + current + " 不能切换到 " + target + "（ROBOT_INVALID_TRANSITION）");
            }
            // 离开自主态前先暂停任务并停住设备，避免「切态后仍按旧任务运动」
            if (current == RobotMode.AUTONOMOUS) {
                pauseRunningTasks(deviceKey);
                hub.sendToBridge(deviceKey, "cmd",
                        envelope("STOP", Map.of(), "MODE_SWITCH"));
            }
            apply(deviceKey, target, operator, "MODE_SWITCH");
            return modeView(deviceKey, target);
        } finally {
            lock.unlock();
        }
    }

    /** 人工确认复位：E_STOP / FAULT → IDLE。 */
    public Map<String, Object> reset(String deviceKey, String operator) {
        registry.requireEnabled(deviceKey);
        ReentrantLock lock = locks.computeIfAbsent(deviceKey, key -> new ReentrantLock());
        lock.lock();
        try {
            RobotMode current = modeOf(deviceKey);
            if (current != RobotMode.E_STOP && current != RobotMode.FAULT) {
                throw new BusinessException(409,
                        "仅急停/故障态需要复位，当前为 " + current + "（ROBOT_INVALID_TRANSITION）");
            }
            RobotMode target = hub.bridgeConnected(deviceKey) ? RobotMode.IDLE : RobotMode.OFFLINE;
            apply(deviceKey, target, operator, "MANUAL_RESET");
            return modeView(deviceKey, target);
        } finally {
            lock.unlock();
        }
    }

    /**
     * 急停：最高优先级旁路，任何态都可执行；即使桥未连接也记录并广播。
     */
    public Map<String, Object> emergencyStop(String deviceKey, String operator) {
        ReentrantLock lock = locks.computeIfAbsent(deviceKey, key -> new ReentrantLock());
        lock.lock();
        try {
            boolean delivered = hub.sendToBridge(deviceKey, "cmd", envelope("STOP", Map.of(), "E_STOP"));
            apply(deviceKey, RobotMode.E_STOP, operator, "E_STOP");
            audit(deviceKey, "E_STOP", "STOP", Map.of(), true, null, operator);
            Map<String, Object> view = modeView(deviceKey, RobotMode.E_STOP);
            view.put("deliveredToBridge", delivered);
            return view;
        } finally {
            lock.unlock();
        }
    }

    /**
     * 下发命令（M1 仅支持人工态运动遥控与喊话/拍照）。
     *
     * @param source CONSOLE（人工态）或 BRAIN（自主态大脑）
     */
    public Map<String, Object> command(String deviceKey, String source, String op,
            Map<String, Object> params, String operator) {
        registry.requireEnabled(deviceKey);
        String normalizedOp = op == null ? "" : op.strip().toUpperCase();

        // STOP 走急停旁路的前置：允许在任意态下发，但仍需白名单与审计
        if ("STOP".equals(normalizedOp)) {
            return emergencyStop(deviceKey, operator);
        }

        Map<String, Object> normalized;
        try {
            normalized = RobotCommandPolicy.normalize(normalizedOp, params);
        } catch (RobotCommandPolicy.RobotPolicyViolation violation) {
            audit(deviceKey, sourceMode(source), normalizedOp, params, false, violation.code(), operator);
            throw new BusinessException(400, violation.getMessage());
        }

        ReentrantLock lock = locks.computeIfAbsent(deviceKey, key -> new ReentrantLock());
        lock.lock();
        try {
            RobotMode current = modeOf(deviceKey);
            String rejectCode = gate(current, source, normalizedOp);
            if (rejectCode != null) {
                audit(deviceKey, current.name(), normalizedOp, normalized, false, rejectCode, operator);
                throw new BusinessException(409, "当前态 " + current + " 不允许该操作（" + rejectCode + "）");
            }
            if (!allowRate(deviceKey)) {
                audit(deviceKey, current.name(), normalizedOp, normalized, false, "ROBOT_RATE_LIMITED", operator);
                throw new BusinessException(429, "命令过于频繁，请降低摇杆或输入频率（ROBOT_RATE_LIMITED）");
            }
            boolean delivered = hub.sendToBridge(deviceKey, "cmd",
                    envelope(normalizedOp, normalized, source));
            if (!delivered) {
                audit(deviceKey, current.name(), normalizedOp, normalized, false, "ROBOT_BRIDGE_OFFLINE", operator);
                throw new BusinessException(503, "蓝牙桥未连接，命令未下发（ROBOT_BRIDGE_OFFLINE）");
            }
            audit(deviceKey, current.name(), normalizedOp, normalized, true, null, operator);
            // 拍照已下发：登记一次视觉巡检意图，等桥回传的关键帧到达后触发识别
            if ("CAPTURE".equals(normalizedOp)) {
                frames.expectCapture(deviceKey, String.valueOf(normalized.getOrDefault("target", "")));
            }
            return Map.of("accepted", true, "op", normalizedOp, "params", normalized, "mode", current.name());
        } finally {
            lock.unlock();
        }
    }

    /**
     * 命令门禁：返回 null 表示允许，否则返回规则码。
     * 运动类命令只能在人工态（CONSOLE）或自主态（BRAIN）下发，
     * 避免「人在遥控时模型插队」与「模型巡检时人工误触」。
     */
    private String gate(RobotMode current, String source, String op) {
        if (current == RobotMode.E_STOP || current == RobotMode.FAULT || current == RobotMode.OFFLINE) {
            return "ROBOT_STATE_BLOCKED";
        }
        boolean motion = "MOVE".equals(op) || "PTZ".equals(op) || "PATROL".equals(op);
        if (motion) {
            if ("BRAIN".equalsIgnoreCase(source)) {
                return current == RobotMode.AUTONOMOUS ? null : "ROBOT_NOT_AUTONOMOUS";
            }
            return current.acceptsMotionCommand() ? null : "ROBOT_NOT_HUMAN_CONTROL";
        }
        // SPEAK / CAPTURE：双态均可，但必须处于在线态
        if (current == RobotMode.IDLE) {
            return "ROBOT_STATE_BLOCKED";
        }
        return null;
    }

    /** 令牌窗口限流：滑动 1 秒。 */
    private boolean allowRate(String deviceKey) {
        Deque<Long> window = commandWindow.computeIfAbsent(deviceKey, key -> new ArrayDeque<>());
        long now = System.currentTimeMillis();
        synchronized (window) {
            while (!window.isEmpty() && now - window.peekFirst() > 1000) {
                window.pollFirst();
            }
            if (window.size() >= RobotCommandPolicy.MAX_COMMANDS_PER_SECOND) {
                return false;
            }
            window.addLast(now);
            return true;
        }
    }

    /**
     * 心跳看门狗：每 200ms 检查一次，沉默超过阈值即 FAULT + STOP。
     * 阈值默认 600ms（3 个心跳周期），符合设计文档。
     */
    @Scheduled(fixedDelay = 200)
    public void heartbeatWatchdog() {
        for (String deviceKey : hub.connectedDeviceKeys()) {
            RobotMode current = modeOf(deviceKey);
            if (current == RobotMode.OFFLINE || current == RobotMode.E_STOP) {
                continue;
            }
            if (hub.silenceMillis(deviceKey) > heartbeatTimeoutMs) {
                ReentrantLock lock = locks.computeIfAbsent(deviceKey, key -> new ReentrantLock());
                if (!lock.tryLock()) {
                    continue;
                }
                try {
                    if (modeOf(deviceKey) != RobotMode.FAULT && modeOf(deviceKey) != RobotMode.E_STOP) {
                        hub.sendToBridge(deviceKey, "cmd", envelope("STOP", Map.of(), "WATCHDOG"));
                        apply(deviceKey, RobotMode.FAULT, "watchdog", "HEARTBEAT_LOST");
                        audit(deviceKey, current.name(), "STOP", Map.of(), false,
                                "ROBOT_HEARTBEAT_LOST", "watchdog");
                    }
                } finally {
                    lock.unlock();
                }
            }
        }
    }

    /** 机队实时视图：状态 + 遥测 + 桥连接，供控制台与自检复用。 */
    public Map<String, Object> liveView(String deviceKey) {
        Map<String, Object> view = modeView(deviceKey, modeOf(deviceKey));
        view.put("telemetry", hub.telemetry(deviceKey));
        view.put("bridgeConnected", hub.bridgeConnected(deviceKey));
        return view;
    }

    private void apply(String deviceKey, RobotMode target, String operator, String reason) {
        modes.put(deviceKey, target);
        try {
            registry.updateStatus(deviceKey, target.name());
        } catch (RuntimeException e) {
            // 台账写入失败不回滚内存状态：设备安全优先，记录后由自检暴露不一致
            log.warn("机器人 {} 状态同步台账失败：{}", deviceKey, e.getMessage());
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("deviceKey", deviceKey);
        payload.put("mode", target.name());
        payload.put("reason", reason);
        payload.put("operator", operator);
        payload.put("ts", Instant.now().toString());
        hub.broadcast("mode", payload);
    }

    private void pauseRunningTasks(String deviceKey) {
        jdbcTemplate.update(
                "UPDATE robot_task SET status = 'PAUSED' WHERE device_key = ? AND status = 'RUNNING'",
                deviceKey);
    }

    private Map<String, Object> modeView(String deviceKey, RobotMode mode) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("deviceKey", deviceKey);
        view.put("mode", mode.name());
        view.put("bridgeConnected", hub.bridgeConnected(deviceKey));
        return view;
    }

    private Map<String, Object> envelope(String op, Map<String, Object> params, String source) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("op", op);
        payload.put("params", params);
        payload.put("source", source);
        return payload;
    }

    private String sourceMode(String source) {
        return "BRAIN".equalsIgnoreCase(source) ? RobotMode.AUTONOMOUS.name() : RobotMode.HUMAN_CONTROL.name();
    }

    private void audit(String deviceKey, String mode, String op, Map<String, Object> params,
            boolean accepted, String rejectCode, String operator) {
        try {
            jdbcTemplate.update(
                    "INSERT INTO robot_command_log (device_key, mode, op, params, accepted, reject_code, operator) "
                            + "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    deviceKey, mode, op, jsonOrNull(params), accepted ? 1 : 0, rejectCode, operator);
        } catch (RuntimeException e) {
            log.warn("机器人命令审计写入失败：{}", e.getMessage());
        }
    }

    private String jsonOrNull(Map<String, Object> params) {
        if (params == null || params.isEmpty()) {
            return null;
        }
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(params);
        } catch (Exception e) {
            return null;
        }
    }
}
