package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.security.SecureRandom;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 多机队调度（M4）。
 *
 * <p>把多个设备的自主巡检归并到同一个 planId，默认并发上限 3（与 DAG 并发上限一致）。
 * RobotBrainService 用 plan_id 字段把设备归属到同一个机队计划，不新建表。
 * 任何失败（设备不在线、IDLE→AUTONOMOUS 切态失败）都只影响该设备，不阻塞其他设备继续启动。</p>
 */
@Slf4j
@Service
public class RobotFleetService {

    private final RobotRegistryService registry;
    private final RobotBrainService brain;
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper mapper;
    private final int concurrency;
    private final ExecutorService executor;

    public RobotFleetService(RobotRegistryService registry,
            RobotBrainService brain,
            JdbcTemplate jdbcTemplate,
            ObjectMapper mapper,
            @Value("${smartops.robot.fleet-concurrency:3}") int concurrency) {
        this.registry = registry;
        this.brain = brain;
        this.jdbcTemplate = jdbcTemplate;
        this.mapper = mapper;
        this.concurrency = Math.max(1, concurrency);
        this.executor = Executors.newFixedThreadPool(this.concurrency, runnable -> {
            Thread thread = new Thread(runnable, "robot-fleet");
            thread.setDaemon(true);
            return thread;
        });
    }

    /**
     * 提交机队巡检。对每个 deviceKey 独立生成 route（同默认环形），并发调度到 RobotBrainService。
     *
     * @param deviceKeys 设备列表；必须 ≥ 2 才叫「机队」，单设备请用 {@link RobotBrainService} 直调
     */
    public Map<String, Object> submit(List<String> deviceKeys, String planId, String operator) {
        if (deviceKeys == null || deviceKeys.size() < 2) {
            throw new BusinessException(400, "机队调度至少需要 2 台设备");
        }
        // 去重 + 保序
        List<String> unique = deviceKeys.stream().distinct().toList();
        String finalPlanId = planId != null && !planId.isBlank()
                ? planId
                : generatePlanId();

        Semaphore sem = new Semaphore(concurrency);
        List<CompletableFuture<DeviceSubmitResult>> futures = new ArrayList<>();
        for (String deviceKey : unique) {
            futures.add(CompletableFuture.supplyAsync(() -> {
                try {
                    sem.acquire();
                    try {
                        Map<String, Object> task = brain.submit(deviceKey, defaultRoute(), finalPlanId, operator);
                        Object idObj = task.get("id");
                        Long taskId = idObj instanceof Number n ? n.longValue() : null;
                        return new DeviceSubmitResult(deviceKey, true, taskId, null);
                    } finally {
                        sem.release();
                    }
                } catch (BusinessException e) {
                    log.warn("机队设备 {} 启动失败：{}", deviceKey, e.getMessage());
                    return new DeviceSubmitResult(deviceKey, false, null, e.getMessage());
                } catch (Exception e) {
                    log.error("机队设备 {} 启动异常", deviceKey, e);
                    return new DeviceSubmitResult(deviceKey, false, null, e.getMessage());
                }
            }, executor));
        }

        // 全部等完（但不阻塞主线程超过 10s）
        try {
            CompletableFuture.allOf(futures.toArray(new CompletableFuture[0]))
                    .orTimeout(10, TimeUnit.SECONDS)
                    .exceptionally(t -> null)
                    .join();
        } catch (Exception ignored) {
            // 个别设备慢不影响汇总
        }

        List<DeviceSubmitResult> results = futures.stream()
                .map(f -> f.isDone() ? f.getNow(null) : new DeviceSubmitResult(
                        "", false, null, "超时未返回"))
                .filter(r -> r != null && !r.deviceKey().isEmpty())
                .toList();

        long accepted = results.stream().filter(DeviceSubmitResult::accepted).count();
        long rejected = results.size() - accepted;

        Map<String, Object> view = new LinkedHashMap<>();
        view.put("planId", finalPlanId);
        view.put("acceptedCount", accepted);
        view.put("rejectedCount", rejected);
        view.put("results", results.stream().map(r -> {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("deviceKey", r.deviceKey());
            map.put("accepted", r.accepted());
            map.put("taskId", r.taskId());
            map.put("message", r.message());
            return map;
        }).toList());
        view.put("planSummary", planSummary(finalPlanId));
        return view;
    }

    /** 按 planId 查机队状态（所有归属于该 plan 的任务）。 */
    public Map<String, Object> planSummary(String planId) {
        List<Map<String, Object>> tasks = jdbcTemplate.queryForList(
                "SELECT id, device_key, status, progress, route, created_at, updated_at "
                        + "FROM robot_task WHERE plan_id = ? ORDER BY id DESC",
                planId);
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("planId", planId);
        summary.put("totalDevices", tasks.stream().map(t -> t.get("device_key")).distinct().count());
        summary.put("running", tasks.stream().filter(t -> "RUNNING".equals(t.get("status"))).count());
        summary.put("paused", tasks.stream().filter(t -> "PAUSED".equals(t.get("status"))).count());
        summary.put("done", tasks.stream().filter(t -> "DONE".equals(t.get("status"))).count());
        summary.put("failed", tasks.stream().filter(t -> "FAILED".equals(t.get("status"))).count());
        summary.put("cancelled", tasks.stream().filter(t -> "CANCELLED".equals(t.get("status"))).count());
        summary.put("tasks", tasks);
        return summary;
    }

    /** 全局暂停 plan 下所有 RUNNING 任务。 */
    public Map<String, Object> pausePlan(String planId, String operator) {
        List<Map<String, Object>> tasks = jdbcTemplate.queryForList(
                "SELECT id FROM robot_task WHERE plan_id = ? AND status = 'RUNNING'", planId);
        int paused = 0;
        for (Map<String, Object> t : tasks) {
            try {
                brain.pause(((Number) t.get("id")).longValue(), operator);
                paused++;
            } catch (BusinessException ignored) {
                // 任务已被其他线程 PAUSE/DONE，忽略
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("planId", planId);
        result.put("pausedCount", paused);
        result.put("planSummary", planSummary(planId));
        return result;
    }

    /** 全局取消 plan 下所有非终态任务。 */
    public Map<String, Object> cancelPlan(String planId, String operator) {
        List<Map<String, Object>> tasks = jdbcTemplate.queryForList(
                "SELECT id, status FROM robot_task WHERE plan_id = ? "
                        + "AND status NOT IN ('DONE', 'CANCELLED', 'FAILED')",
                planId);
        int cancelled = 0;
        for (Map<String, Object> t : tasks) {
            try {
                brain.cancel(((Number) t.get("id")).longValue(), operator);
                cancelled++;
            } catch (BusinessException ignored) {
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("planId", planId);
        result.put("cancelledCount", cancelled);
        result.put("planSummary", planSummary(planId));
        return result;
    }

    /** 全局机队汇总（前端面板用）：正在执行的所有 plan。 */
    public Map<String, Object> fleetStatus() {
        List<Map<String, Object>> plans = jdbcTemplate.queryForList(
                "SELECT plan_id, COUNT(*) AS total, "
                        + "SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) AS running, "
                        + "SUM(CASE WHEN status='PAUSED' THEN 1 ELSE 0 END) AS paused, "
                        + "SUM(CASE WHEN status='DONE' THEN 1 ELSE 0 END) AS done, "
                        + "SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed, "
                        + "SUM(CASE WHEN status='CANCELLED' THEN 1 ELSE 0 END) AS cancelled, "
                        + "MAX(updated_at) AS updated_at "
                        + "FROM robot_task WHERE plan_id IS NOT NULL GROUP BY plan_id ORDER BY updated_at DESC LIMIT 20");
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("concurrency", concurrency);
        view.put("plans", plans);
        return view;
    }

    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------

    private static final SecureRandom RAND = new SecureRandom();

    private static String generatePlanId() {
        long ts = Instant.now().toEpochMilli();
        byte[] bytes = new byte[3];
        RAND.nextBytes(bytes);
        int hexInt = ((bytes[0] & 0xFF) << 16) | ((bytes[1] & 0xFF) << 8) | (bytes[2] & 0xFF);
        // 用 Instant 取年月日时分秒（%tY 等需要 TemporalAccessor，long ts 不行）
        java.time.LocalDateTime now = java.time.LocalDateTime.ofInstant(
                java.time.Instant.ofEpochMilli(ts), java.time.ZoneId.systemDefault());
        return String.format("PLAN-%04d%02d%02d-%02d%02d%02d-%06x",
                now.getYear(), now.getMonthValue(), now.getDayOfMonth(),
                now.getHour(), now.getMinute(), now.getSecond(),
                hexInt);
    }

    private static List<Map<String, Object>> defaultRoute() {
        List<Map<String, Object>> route = new ArrayList<>();
        for (double theta : new double[]{0, 90, 180, 270}) {
            Map<String, Object> point = new LinkedHashMap<>();
            point.put("x", theta == 0 || theta == 270 ? 0.0 : 3.0);
            point.put("y", theta == 0 || theta == 90 ? 0.0 : 3.0);
            point.put("theta", theta);
            point.put("label", "路点-" + (theta == 0 ? "北" : theta == 90 ? "东" : theta == 180 ? "南" : "西"));
            point.put("actions", List.of("CAPTURE"));
            route.add(point);
        }
        return route;
    }

    private record DeviceSubmitResult(String deviceKey, boolean accepted, Long taskId, String message) { }
}
