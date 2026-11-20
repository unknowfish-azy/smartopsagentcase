package com.smartops.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.robot.RobotMode;
import com.smartops.robot.RobotTelemetryHub;
import com.smartops.robot.replan.DeterministicReplan;
import com.smartops.robot.replan.OllamaReplan;
import com.smartops.robot.replan.ReplanStrategy;
import com.smartops.robot.replan.ReplanStrategy.ReplanResult;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

/**
 * 机器人自主态大脑（M3）。
 *
 * <p>核心职责：
 * <ol>
 *   <li>受理 route 巡检任务，状态流转 PENDING → RUNNING → DONE/PAUSED/FAILED/CANCELLED；</li>
 *   <li>执行器逐点下发 MOVE/CAPTURE：每步由 timer 触发（无真机，不能依赖真实里程计到达事件），
 *       超时后视为到达下一节点；</li>
 *   <li>切 AUTONOMOUS 态（当前 IDLE 且桥在线才自动切；否则返回 409 让前端引导人工态）；</li>
 *   <li>失败/取消时下发 STOP；暂停时仅停运动命令，任务保留 planId 供续跑；</li>
 *   <li>任何时刻切离开 AUTONOMOUS 态 → 进行中任务被置 PAUSED（由 {@link RobotControlService} 触发）。</li>
 * </ol>
 */
@Slf4j
@Service
public class RobotBrainService {

    /** 每个 MOVE 命令的 ttl（dead-man switch，毫秒），由桥侧 watchdog 自动停。 */
    private static final int MOVE_TTL_MS = 400;
    /** 到达单路点后的等待时间（毫秒）：无真机里程计，用固定等待模拟「到达 + 识别」。 */
    private static final long WAYPOINT_DWELL_MS = 2500L;
    /** 目标坐标路点：到达判定半径（米）。 */
    private static final double NAV_ARRIVE_RADIUS = 0.35;
    /** 目标坐标路点：单点闭环导航超时（毫秒）。 */
    private static final long NAV_TIMEOUT_MS = 30_000L;
    /** 目标坐标路点：闭环导航控制节拍（毫秒）。 */
    private static final long NAV_TICK_MS = 400L;
    /** 执行并发上限（多机队调度时会由 FleetService 的外部并发进一步限制）。 */
    private final int parallelism;

    private final RobotRegistryService registry;
    private final RobotControlService control;
    private final RobotTelemetryHub hub;
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper mapper;
    private final ExecutorService executor;
    private final InspectorEventService inspectorEvents;

    /** 重规划触发阈值：同 device_key 在窗口内连续 WARN/CRITICAL 条数。 */
    private final int replanThreshold;
    /** 重规划事件查询窗口（毫秒）。 */
    private final long replanWindowMs;
    /** 主重规划策略：deterministic（默认）/ ollama。 */
    private final ReplanStrategy primaryStrategy;
    /** 兜底策略（始终可用）。 */
    private final ReplanStrategy fallbackStrategy;

    /** taskId → 执行中的 future（用于取消/暂停）。 */
    private final Map<Long, Future<?>> running = new ConcurrentHashMap<>();
    /** taskId → 上次重规划时间戳（毫秒，冷却防死循环）。 */
    private final Map<Long, Long> lastReplanAt = new ConcurrentHashMap<>();
    /** 重规划最小冷却时间（毫秒）：同任务两次重规划至少间隔此值。 */
    private static final long REPLAN_COOLDOWN_MS = 15_000L;

    public RobotBrainService(RobotRegistryService registry,
            RobotControlService control,
            RobotTelemetryHub hub,
            JdbcTemplate jdbcTemplate,
            ObjectMapper mapper,
            InspectorEventService inspectorEvents,
            List<ReplanStrategy> strategies,
            @Value("${smartops.robot.brain-parallelism:4}") int parallelism,
            @Value("${smartops.robot.replan.threshold:2}") int replanThreshold,
            @Value("${smartops.robot.replan.window-ms:30000}") long replanWindowMs,
            @Value("${smartops.robot.replan.strategy:deterministic}") String primary) {
        this.registry = registry;
        this.control = control;
        this.hub = hub;
        this.jdbcTemplate = jdbcTemplate;
        this.mapper = mapper;
        this.inspectorEvents = inspectorEvents;
        this.parallelism = Math.max(1, parallelism);
        this.replanThreshold = Math.max(1, replanThreshold);
        this.replanWindowMs = Math.max(1000L, replanWindowMs);

        // 策略选择：按 primary 名匹配；deterministic 始终存在作为兜底
        Map<String, ReplanStrategy> byName = new LinkedHashMap<>();
        if (strategies != null) {
            for (ReplanStrategy s : strategies) byName.put(s.name().split("-")[0], s);
        }
        this.fallbackStrategy = byName.getOrDefault("deterministic", new DeterministicReplan());
        this.primaryStrategy = byName.getOrDefault(primary, this.fallbackStrategy);

        this.executor = Executors.newFixedThreadPool(this.parallelism, runnable -> {
            Thread thread = new Thread(runnable, "robot-brain");
            thread.setDaemon(true);
            return thread;
        });
    }

    /**
     * 受理自主巡检任务。
     *
     * @param route    路点列表，每点含 x/y/theta 与可选 actions（默认 ["CAPTURE"]）
     * @param planId   可选 agent DAG planId，断点续跑用
     * @param operator 操作人（审计）
     */
    public Map<String, Object> submit(String deviceKey, List<Map<String, Object>> route,
            String planId, String operator) {
        registry.requireEnabled(deviceKey);
        RobotMode mode = control.modeOf(deviceKey);
        if (mode != RobotMode.IDLE || !isBridgeOnline(deviceKey)) {
            throw new BusinessException(409,
                    "仅 IDLE 且桥在线时可启动自主巡检（当前 " + mode + "）");
        }
        if (route == null || route.isEmpty()) {
            throw new BusinessException(400, "route 不能为空");
        }
        // 自动切 AUTONOMOUS（失败则 409 让前端引导用户先复位）
        Map<String, Object> modeView;
        try {
            modeView = control.switchMode(deviceKey, RobotMode.AUTONOMOUS, operator);
        } catch (BusinessException e) {
            throw new BusinessException(409,
                    "无法切换到自主态：" + e.getMessage());
        }

        String routeJson;
        try {
            routeJson = mapper.writeValueAsString(route);
        } catch (Exception e) {
            throw new BusinessException(400, "route JSON 序列化失败");
        }

        jdbcTemplate.update("""
                INSERT INTO robot_task (device_key, plan_id, route, progress)
                VALUES (?, ?, ?, 0)
                """, deviceKey, planId, routeJson);
        long taskId = jdbcTemplate.queryForObject("SELECT LAST_INSERT_ID()", Long.class);
        jdbcTemplate.update("UPDATE robot_task SET status = 'RUNNING' WHERE id = ?", taskId);

        Future<?> future = executor.submit(() -> runTask(taskId, deviceKey, route, operator));
        running.put(taskId, future);

        Map<String, Object> result = taskView(taskId);
        result.put("modeView", modeView);
        return result;
    }

    /** 人工接管：暂停所有运行中任务（控制层切换态时已自动 pause，这里可独立调用）。 */
    public Map<String, Object> pause(Long taskId, String operator) {
        int updated = jdbcTemplate.update(
                "UPDATE robot_task SET status = 'PAUSED' WHERE id = ? AND status = 'RUNNING'", taskId);
        if (updated == 0) {
            throw new BusinessException(409, "任务已结束或不在运行态");
        }
        Future<?> future = running.remove(taskId);
        if (future != null) {
            future.cancel(true);
        }
        return taskView(taskId);
    }

    /** 续跑：仅支持 PAUSED 任务，从上次 progress 继续。 */
    public Map<String, Object> resume(Long taskId, String operator) {
        Map<String, Object> task = jdbcTemplate.queryForMap(
                "SELECT id, device_key, route, progress FROM robot_task WHERE id = ?", taskId);
        String deviceKey = (String) task.get("device_key");
        RobotMode mode = control.modeOf(deviceKey);
        if (mode != RobotMode.IDLE && mode != RobotMode.AUTONOMOUS) {
            throw new BusinessException(409, "当前态 " + mode + " 不可续跑（需 IDLE 或 AUTONOMOUS）");
        }
        if (mode == RobotMode.IDLE && !isBridgeOnline(deviceKey)) {
            throw new BusinessException(409, "桥未连接，无法续跑");
        }
        if (mode == RobotMode.IDLE) {
            control.switchMode(deviceKey, RobotMode.AUTONOMOUS, operator);
        }
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> route = parseRoute((String) task.get("route"));
        int progress = ((Number) task.get("progress")).intValue();
        if (progress >= route.size()) {
            throw new BusinessException(409, "任务已完成（progress=" + progress + "）");
        }
        jdbcTemplate.update("UPDATE robot_task SET status = 'RUNNING' WHERE id = ?", taskId);
        Future<?> future = executor.submit(() -> runTaskFrom(taskId, deviceKey, route, progress, operator));
        running.put(taskId, future);
        return taskView(taskId);
    }

    /** 取消：任意态都允许，设备立即 STOP。 */
    public Map<String, Object> cancel(Long taskId, String operator) {
        Map<String, Object> task = jdbcTemplate.queryForMap(
                "SELECT id, device_key, status FROM robot_task WHERE id = ?", taskId);
        String status = (String) task.get("status");
        if ("DONE".equals(status) || "CANCELLED".equals(status) || "FAILED".equals(status)) {
            throw new BusinessException(409, "任务已结束");
        }
        String deviceKey = (String) task.get("device_key");
        Future<?> future = running.remove(taskId);
        if (future != null) {
            future.cancel(true);
        }
        jdbcTemplate.update("UPDATE robot_task SET status = 'CANCELLED' WHERE id = ?", taskId);
        try {
            control.emergencyStop(deviceKey, operator);
        } catch (BusinessException ignored) {
            // 设备已在 E_STOP 也 OK
        }
        return taskView(taskId);
    }

    /** 指定设备的最近任务列表。 */
    public List<Map<String, Object>> list(String deviceKey) {
        return jdbcTemplate.queryForList(
                "SELECT id, device_key, plan_id, route, status, progress, created_at, updated_at "
                        + "FROM robot_task WHERE device_key = ? ORDER BY id DESC LIMIT 100",
                deviceKey);
    }

    /** 全机队任务视图（供前端机队面板）。 */
    public Map<String, Object> summary() {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("running", jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM robot_task WHERE status = 'RUNNING'", Long.class));
        view.put("paused", jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM robot_task WHERE status = 'PAUSED'", Long.class));
        view.put("failed", jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM robot_task WHERE status = 'FAILED'", Long.class));
        return view;
    }

    /** 任务超长时间后自动清理 future（异常场景兜底）。 */
    @Scheduled(fixedDelay = 30_000)
    public void cleanupTerminated() {
        running.entrySet().removeIf(entry -> entry.getValue().isDone());
    }

    // ------------------------------------------------------------------
    // 执行器
    // ------------------------------------------------------------------

    private void runTask(long taskId, String deviceKey, List<Map<String, Object>> route, String operator) {
        runTaskFrom(taskId, deviceKey, route, 0, operator);
    }

    private void runTaskFrom(long taskId, String deviceKey, List<Map<String, Object>> route,
            int startIndex, String operator) {
        try {
            int progress = startIndex;
            List<Map<String, Object>> activeRoute = new ArrayList<>(route);
            int i = startIndex;
            while (i < activeRoute.size()) {
                if (Thread.currentThread().isInterrupted()) {
                    break; // cancel/pause
                }
                if (!"RUNNING".equals(currentStatus(taskId))) {
                    break; // DB 侧已被人工暂停/取消
                }
                Map<String, Object> point = activeRoute.get(i);
                executeWaypoint(deviceKey, point, operator, taskId);
                progress = i + 1;
                jdbcTemplate.update("UPDATE robot_task SET progress = ? WHERE id = ?", progress, taskId);

                // M6: 连续异常重规划 —— 查询窗口内 WARN/CRITICAL 数量
                if (shouldReplan(deviceKey, taskId)) {
                    String before = activeRoute.size() + "@" + i;
                    activeRoute = replanAround(activeRoute, i, deviceKey, taskId);
                    jdbcTemplate.update("UPDATE robot_task SET route = ? WHERE id = ?",
                            mapper.writeValueAsString(activeRoute), taskId);
                    log.info("任务 {} 触发重规划：{} 路点 → {} 路点", taskId, before,
                            activeRoute.size() + "@" + i);
                    // 重规划后路点数量变了，保持当前 i 继续执行
                    continue;
                }
                i++;
            }
            String finalStatus;
            String current = currentStatus(taskId);
            if ("CANCELLED".equals(current)) {
                return;
            }
            finalStatus = Thread.currentThread().isInterrupted() ? "PAUSED"
                    : "PAUSED".equals(current) ? "PAUSED"
                    : "DONE";
            jdbcTemplate.update("UPDATE robot_task SET status = ? WHERE id = ?", finalStatus, taskId);
        } catch (BusinessException e) {
            log.warn("自主任务 {} 失败：{}", taskId, e.getMessage());
            jdbcTemplate.update("UPDATE robot_task SET status = 'FAILED' WHERE id = ?", taskId);
            try {
                control.emergencyStop(deviceKey, "brain");
            } catch (BusinessException ignored) {
            }
        } catch (Exception e) {
            log.error("自主任务 {} 异常", taskId, e);
            jdbcTemplate.update("UPDATE robot_task SET status = 'FAILED' WHERE id = ?", taskId);
        } finally {
            running.remove(taskId);
            lastReplanAt.remove(taskId);
        }
    }

    // ------------------------------------------------------------------
    // M6 连续异常重规划
    // ------------------------------------------------------------------

    /** 查询 device_key 在窗口内的 WARN/CRITICAL 纠察事件条数（task_id 前缀 robot-deviceKey）。 */
    private boolean shouldReplan(String deviceKey, long taskId) {
        // 冷却期：同任务 15s 内不重复重规划（防止 simulated-abnormal 触发后无限原地循环）
        long now = System.currentTimeMillis();
        Long last = lastReplanAt.get(taskId);
        if (last != null && now - last < REPLAN_COOLDOWN_MS) {
            return false;
        }

        LocalDateTime since = LocalDateTime.now().minus(java.time.Duration.ofMillis(replanWindowMs));
        int count = jdbcTemplate.queryForObject("""
                SELECT COUNT(*) FROM inspector_event
                WHERE task_id LIKE ? AND severity IN ('WARN', 'CRITICAL')
                  AND created_at >= ?
                """, Integer.class,
                "robot-" + deviceKey + "-%", since);
        boolean trigger = count >= replanThreshold;
        if (trigger) {
            log.info("任务 {} 触发重规划：deviceKey={} 窗口内 WARN/CRITICAL={} ≥ 阈值={}",
                    taskId, deviceKey, count, replanThreshold);
        }
        return trigger;
    }

    /**
     * 重规划执行入口 —— 先走 primaryStrategy（M7 可配置 ollama 等），
     * fallback 时自动降级到 deterministic（始终可用）。
     *
     * <p>fail-closed：任何策略异常都不会阻塞任务。</p>
     */
    private List<Map<String, Object>> replanAround(List<Map<String, Object>> route,
            int currentIndex, String deviceKey, long taskId) {
        lastReplanAt.put(taskId, System.currentTimeMillis());
        ReplanResult result = primaryStrategy.replan(route, currentIndex, deviceKey);
        if (result.isFallback()) {
            log.warn("主重规划策略 {} 请求兜底（{}ms）：{}",
                    primaryStrategy.name(), result.elapsedMs(), ((ReplanStrategy.FallbackResult) result).reason());
            result = fallbackStrategy.replan(route, currentIndex, deviceKey);
        }
        if (result.isFallback()) {
            // 兜底策略也失败（几乎不可能）—— 返回原 route 让 while 循环 continue 执行下一个路点
            log.error("重规划失败：主策略和兜底策略都返回 fallback，继续执行原 route");
            return route;
        }
        ReplanStrategy.SuccessResult success = (ReplanStrategy.SuccessResult) result;
        log.info("重规划由 [{}] 生成（耗时 {}ms），绕行点标签已写回 DB",
                success.routeSource(), success.elapsedMs());
        return success.newRoute();
    }

    /** 单个路点的执行：目标坐标走闭环导航，否则沿用归一化向量步进；随后执行 actions。 */
    private void executeWaypoint(String deviceKey, Map<String, Object> point, String operator, long taskId) {
        boolean hasTarget = point.get("targetX") != null && point.get("targetY") != null;
        if (hasTarget) {
            // 地图规划出的绝对坐标路点：按真实遥测闭环趋近，到达后再执行动作
            if (!navigateTo(deviceKey, num(point.get("targetX")), num(point.get("targetY")), taskId, operator)) {
                return;
            }
        } else {
            double theta = num(point.get("theta"));

            // MOVE 命令参数：policy 已把 x/y/theta 都定义为 [-1,1] 归一化量
            // （theta 这里当作 angular velocity 方向用，而非绝对角度）
            Map<String, Object> moveParams = new LinkedHashMap<>();
            moveParams.put("x", clamp(num(point.get("x")), -1.0, 1.0));
            moveParams.put("y", clamp(num(point.get("y")), -1.0, 1.0));
            moveParams.put("theta", clamp(theta, -1.0, 1.0));
            moveParams.put("speed", 0.4);
            moveParams.put("ttlMs", MOVE_TTL_MS);
            control.command(deviceKey, "BRAIN", "MOVE", moveParams, operator);

            // 模拟运动：等待后认为到达（无真机里程计）
            try {
                Thread.sleep(WAYPOINT_DWELL_MS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }

        @SuppressWarnings("unchecked")
        List<String> actions = point.containsKey("actions")
                ? (List<String>) point.get("actions")
                : List.of("CAPTURE");

        for (String action : actions) {
            try {
                if ("CAPTURE".equalsIgnoreCase(action)) {
                    Map<String, Object> captureParams = Map.of("target",
                            point.getOrDefault("label", "路点"));
                    control.command(deviceKey, "BRAIN", "CAPTURE", captureParams, operator);
                    Thread.sleep(WAYPOINT_DWELL_MS / 2);
                } else if ("SPEAK".equalsIgnoreCase(action)) {
                    Map<String, Object> speakParams = Map.of("text",
                            point.getOrDefault("speech", "通过路点"));
                    control.command(deviceKey, "BRAIN", "SPEAK", speakParams, operator);
                }
            } catch (BusinessException e) {
                log.warn("路点动作 {} 被拒：{}", action, e.getMessage());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    /**
     * 绝对坐标路点的闭环导航：读取最近遥测位姿，计算方位误差后按节拍续发 MOVE，
     * 到达判定半径内或超时即停。任务被暂停/取消时立即中断，最终一定补发 STOP。
     *
     * @return true 表示可继续执行该路点动作；false 表示任务已中断
     */
    private boolean navigateTo(String deviceKey, double targetX, double targetY,
            long taskId, String operator) {
        long deadline = System.currentTimeMillis() + NAV_TIMEOUT_MS;
        boolean arrived = false;
        try {
            while (System.currentTimeMillis() < deadline) {
                if (!"RUNNING".equals(currentStatus(taskId))) {
                    return false;
                }
                Map<String, Object> snapshot = hub.telemetry(deviceKey);
                Object poseRaw = snapshot == null ? null : snapshot.get("pose");
                if (!(poseRaw instanceof Map<?, ?> pose)) {
                    Thread.sleep(NAV_TICK_MS);
                    continue;
                }
                double x = num(pose.get("x"));
                double y = num(pose.get("y"));
                double dx = targetX - x;
                double dy = targetY - y;
                double distance = Math.hypot(dx, dy);
                if (distance <= NAV_ARRIVE_RADIUS) {
                    arrived = true;
                    break;
                }
                double error = normalizeDegrees(
                        Math.toDegrees(Math.atan2(dy, dx)) - num(pose.get("theta")));
                boolean turning = Math.abs(error) > 35.0;
                Map<String, Object> moveParams = new LinkedHashMap<>();
                // 大角度先原地转向，小角度再边走边修正；x/y 仍是车体归一化分量
                moveParams.put("x", turning ? 0.0 : clamp(Math.cos(Math.toRadians(error)), -1.0, 1.0));
                moveParams.put("y", turning ? 0.0 : clamp(Math.sin(Math.toRadians(error)), -1.0, 1.0));
                moveParams.put("theta", clamp(error / 45.0, -1.0, 1.0));
                // 临近目标减速，避免在到达半径附近来回振荡
                moveParams.put("speed", distance < 1.2 ? 0.25 : 0.6);
                moveParams.put("ttlMs", MOVE_TTL_MS);
                control.command(deviceKey, "BRAIN", "MOVE", moveParams, operator);
                Thread.sleep(NAV_TICK_MS);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        } catch (RuntimeException e) {
            log.warn("路点导航异常 device={} target=({},{}): {}", deviceKey,
                    targetX, targetY, e.getMessage());
        } finally {
            try {
                control.command(deviceKey, "BRAIN", "STOP", Map.of(), operator);
            } catch (RuntimeException e) {
                log.debug("导航结束补发 STOP 失败 device={}: {}", deviceKey, e.getMessage());
            }
        }
        if (!arrived) {
            log.warn("路点导航未在 {}ms 内到达 device={} target=({},{})",
                    NAV_TIMEOUT_MS, deviceKey, targetX, targetY);
        }
        return true;
    }


    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------

    private boolean isBridgeOnline(String deviceKey) {
        return hub.bridgeConnected(deviceKey);
    }

    private String currentStatus(long taskId) {
        List<String> rows = jdbcTemplate.query(
                "SELECT status FROM robot_task WHERE id = ?",
                (rs, i) -> rs.getString(1),
                taskId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private List<Map<String, Object>> parseRoute(String json) {
        try {
            return mapper.readValue(json, new TypeReference<>() {});
        } catch (Exception e) {
            throw new BusinessException(400, "route 解析失败");
        }
    }

    private Map<String, Object> taskView(long taskId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT id, device_key, plan_id, route, status, progress, created_at, updated_at "
                        + "FROM robot_task WHERE id = ?", taskId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private double num(Object value) {
        if (value == null) return 0.0;
        if (value instanceof Number n) return n.doubleValue();
        try {
            return Double.parseDouble(String.valueOf(value));
        } catch (NumberFormatException e) {
            return 0.0;
        }
    }

    private static double clamp(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }

    /** 角度归一化到 (-180, 180]，用于计算最短转向方向。 */
    private static double normalizeDegrees(double value) {
        double angle = value % 360.0;
        if (angle > 180.0) angle -= 360.0;
        if (angle < -180.0) angle += 360.0;
        return angle;
    }

    @PreDestroy
    void shutdown() {
        executor.shutdownNow();
        try {
            executor.awaitTermination(2, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
        }
    }
}
