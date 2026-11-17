package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.dto.robot.RobotCommandRequest;
import com.smartops.dto.robot.RobotDeviceUpsertRequest;
import com.smartops.dto.robot.RobotEnabledRequest;
import com.smartops.dto.robot.RobotModeRequest;
import com.smartops.robot.RobotMode;
import com.smartops.security.CurrentSessions;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.service.RobotBrainService;
import com.smartops.service.RobotControlService;
import com.smartops.service.RobotFleetService;
import com.smartops.service.RobotFrameService;
import com.smartops.service.RobotRegistryService;
import com.smartops.service.RobotVoiceService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 巡检机器人接口（M0 台账 + M1 双态控制）。
 *
 * <p>读接口要求登录会话；写接口（登记/启停/双态/遥控）额外要求 {@code admin.config}
 * 能力并留安全审计。急停例外：任何登录用户都可触发（安全优先），但同样审计。</p>
 */
@RestController
@RequestMapping("/api/robot")
@RequiredArgsConstructor
public class RobotController {

    private final RobotRegistryService registry;
    private final RobotControlService control;
    private final RobotFrameService frames;
    private final RobotBrainService brain;
    private final RobotVoiceService voice;
    private final RobotFleetService fleet;
    private final UserAccountService accounts;
    private final SecurityAuditService audit;

    @GetMapping("/devices")
    public ApiResponse<List<Map<String, Object>>> devices(HttpServletRequest request) {
        CurrentSessions.require(request);
        return ApiResponse.success(registry.listDevices());
    }

    @PostMapping("/devices")
    public ApiResponse<Map<String, Object>> upsertDevice(
            HttpServletRequest request,
            @Valid @RequestBody RobotDeviceUpsertRequest body) {
        requireConfigurator(request, "ROBOT_DEVICE_UPSERT", body.getDeviceKey());
        return ApiResponse.success(registry.upsert(body));
    }

    @PutMapping("/devices/{deviceKey}/enabled")
    public ApiResponse<Map<String, Object>> setEnabled(
            HttpServletRequest request,
            @PathVariable String deviceKey,
            @Valid @RequestBody RobotEnabledRequest body) {
        requireConfigurator(request, "ROBOT_DEVICE_ENABLED", deviceKey);
        return ApiResponse.success(registry.setEnabled(deviceKey, Boolean.TRUE.equals(body.getEnabled())));
    }

    @GetMapping("/devices/{deviceKey}/status")
    public ApiResponse<Map<String, Object>> deviceStatus(
            HttpServletRequest request,
            @PathVariable String deviceKey) {
        CurrentSessions.require(request);
        return ApiResponse.success(registry.deviceStatus(deviceKey));
    }

    /** 机队自检：真实反映桥配置与设备状态分布，不伪装在线。 */
    @GetMapping("/status")
    public ApiResponse<Map<String, Object>> status(HttpServletRequest request) {
        CurrentSessions.require(request);
        return ApiResponse.success(registry.fleetStatus());
    }

    /** 实时视图：运行态 + 最新遥测 + 桥连接，供控制台首屏渲染。 */
    @GetMapping("/devices/{deviceKey}/live")
    public ApiResponse<Map<String, Object>> live(
            HttpServletRequest request,
            @PathVariable String deviceKey) {
        CurrentSessions.require(request);
        registry.deviceStatus(deviceKey);
        return ApiResponse.success(control.liveView(deviceKey));
    }

    /** 最新关键帧 + 最近一次视觉结论（控制台刷新后回填用）；无帧时 data 为 null。 */
    @GetMapping("/devices/{deviceKey}/frame")
    public ApiResponse<Map<String, Object>> latestFrame(
            HttpServletRequest request,
            @PathVariable String deviceKey) {
        CurrentSessions.require(request);
        registry.deviceStatus(deviceKey);
        return ApiResponse.success(frames.latestFrame(deviceKey));
    }

    /** 双态切换（人工态 ⇄ 自主态）；自主态转人工态会暂停进行中的任务。 */
    @PostMapping("/devices/{deviceKey}/mode")
    public ApiResponse<Map<String, Object>> switchMode(
            HttpServletRequest request,
            @PathVariable String deviceKey,
            @Valid @RequestBody RobotModeRequest body) {
        SessionUser user = requireConfigurator(request, "ROBOT_MODE_SWITCH", deviceKey);
        RobotMode target;
        try {
            target = RobotMode.valueOf(body.getMode().strip().toUpperCase());
        } catch (IllegalArgumentException e) {
            throw new com.smartops.exception.BusinessException(400,
                    "mode 仅允许 AUTONOMOUS/HUMAN_CONTROL/IDLE（ROBOT_INVALID_MODE）");
        }
        return ApiResponse.success(control.switchMode(deviceKey, target, user.username()));
    }

    /** 命令下发（与 WebSocket 通道共用白名单/钳位/限流/审计）。 */
    @PostMapping("/devices/{deviceKey}/command")
    public ApiResponse<Map<String, Object>> command(
            HttpServletRequest request,
            @PathVariable String deviceKey,
            @Valid @RequestBody RobotCommandRequest body) {
        SessionUser user = requireConfigurator(request, "ROBOT_COMMAND", deviceKey);
        String source = body.getSource() == null || body.getSource().isBlank()
                ? "CONSOLE" : body.getSource();
        return ApiResponse.success(control.command(
                deviceKey, source, body.getOp(), body.getParams(), user.username()));
    }

    /** 急停：任何登录用户都可触发（安全优先，不受 admin.config 限制）。 */
    @PostMapping("/devices/{deviceKey}/estop")
    public ApiResponse<Map<String, Object>> emergencyStop(
            HttpServletRequest request,
            @PathVariable String deviceKey) {
        SessionUser user = CurrentSessions.require(request);
        audit.record(user, "ROBOT_ESTOP", deviceKey, "ALLOWED");
        return ApiResponse.success(control.emergencyStop(deviceKey, user.username()));
    }

    /** 人工复位：急停/故障态回到空闲（桥在线回 IDLE，否则 OFFLINE）。 */
    @PostMapping("/devices/{deviceKey}/reset")
    public ApiResponse<Map<String, Object>> reset(
            HttpServletRequest request,
            @PathVariable String deviceKey) {
        SessionUser user = requireConfigurator(request, "ROBOT_RESET", deviceKey);
        return ApiResponse.success(control.reset(deviceKey, user.username()));
    }

    // ------------------------------------------------------------------
    // M3 自主态大脑
    // ------------------------------------------------------------------

    /** 受理自主巡检任务（route 自动生成或前端传入）。 */
    @PostMapping("/devices/{deviceKey}/tasks")
    public ApiResponse<Map<String, Object>> submitTask(
            HttpServletRequest request,
            @PathVariable String deviceKey,
            @RequestBody Map<String, Object> body) {
        SessionUser user = requireConfigurator(request, "ROBOT_TASK_SUBMIT", deviceKey);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> route = (List<Map<String, Object>>) body.get("route");
        String planId = body.get("planId") == null ? null : String.valueOf(body.get("planId"));
        if (route == null || route.isEmpty()) {
            route = defaultPatrolRoute();
        }
        return ApiResponse.success(brain.submit(deviceKey, route, planId, user.username()));
    }

    /** 指定设备的任务列表（最近 100 条）。 */
    @GetMapping("/devices/{deviceKey}/tasks")
    public ApiResponse<List<Map<String, Object>>> tasks(
            HttpServletRequest request,
            @PathVariable String deviceKey) {
        CurrentSessions.require(request);
        return ApiResponse.success(brain.list(deviceKey));
    }

    /** 机队任务汇总（RUNNING/PAUSED/FAILED 数量，前端面板展示用）。 */
    @GetMapping("/tasks/summary")
    public ApiResponse<Map<String, Object>> taskSummary(HttpServletRequest request) {
        CurrentSessions.require(request);
        return ApiResponse.success(brain.summary());
    }

    @PostMapping("/tasks/{id}/pause")
    public ApiResponse<Map<String, Object>> pauseTask(
            HttpServletRequest request, @PathVariable Long id) {
        SessionUser user = requireConfigurator(request, "ROBOT_TASK_PAUSE", String.valueOf(id));
        return ApiResponse.success(brain.pause(id, user.username()));
    }

    @PostMapping("/tasks/{id}/resume")
    public ApiResponse<Map<String, Object>> resumeTask(
            HttpServletRequest request, @PathVariable Long id) {
        SessionUser user = requireConfigurator(request, "ROBOT_TASK_RESUME", String.valueOf(id));
        return ApiResponse.success(brain.resume(id, user.username()));
    }

    @PostMapping("/tasks/{id}/cancel")
    public ApiResponse<Map<String, Object>> cancelTask(
            HttpServletRequest request, @PathVariable Long id) {
        SessionUser user = requireConfigurator(request, "ROBOT_TASK_CANCEL", String.valueOf(id));
        return ApiResponse.success(brain.cancel(id, user.username()));
    }

    /** 语音指令入口：文本经注入检测 → 词表匹配 → 转对应控制命令。 */
    @PostMapping("/devices/{deviceKey}/voice")
    public ApiResponse<Map<String, Object>> voice(
            HttpServletRequest request,
            @PathVariable String deviceKey,
            @RequestBody Map<String, String> body) {
        SessionUser user = requireConfigurator(request, "ROBOT_VOICE", deviceKey);
        String text = body == null ? null : body.get("text");
        return ApiResponse.success(voice.handle(deviceKey, text, user.username()));
    }

    // ------------------------------------------------------------------
    // M4 机队调度
    // ------------------------------------------------------------------

    /** 提交机队巡检（≥2 台设备，默认并发 3）。 */
    @PostMapping("/fleet/submit")
    public ApiResponse<Map<String, Object>> submitFleet(
            HttpServletRequest request,
            @RequestBody Map<String, Object> body) {
        SessionUser user = requireConfigurator(request, "ROBOT_FLEET_SUBMIT", "fleet");
        @SuppressWarnings("unchecked")
        List<String> deviceKeys = (List<String>) body.get("deviceKeys");
        String planId = body.get("planId") == null ? null : String.valueOf(body.get("planId"));
        return ApiResponse.success(fleet.submit(deviceKeys, planId, user.username()));
    }

    /** 按 planId 查机队所有子任务状态。 */
    @GetMapping("/fleet/{planId}")
    public ApiResponse<Map<String, Object>> fleetPlan(HttpServletRequest request, @PathVariable String planId) {
        CurrentSessions.require(request);
        return ApiResponse.success(fleet.planSummary(planId));
    }

    /** 全局暂停 plan 下所有 RUNNING 子任务。 */
    @PostMapping("/fleet/{planId}/pause")
    public ApiResponse<Map<String, Object>> pauseFleet(
            HttpServletRequest request, @PathVariable String planId) {
        SessionUser user = requireConfigurator(request, "ROBOT_FLEET_PAUSE", planId);
        return ApiResponse.success(fleet.pausePlan(planId, user.username()));
    }

    /** 全局取消 plan 下所有非终态子任务。 */
    @PostMapping("/fleet/{planId}/cancel")
    public ApiResponse<Map<String, Object>> cancelFleet(
            HttpServletRequest request, @PathVariable String planId) {
        SessionUser user = requireConfigurator(request, "ROBOT_FLEET_CANCEL", planId);
        return ApiResponse.success(fleet.cancelPlan(planId, user.username()));
    }

    /** 机队总体状态（最近 20 个 plan 的汇总）。 */
    @GetMapping("/fleet/status")
    public ApiResponse<Map<String, Object>> fleetStatus(HttpServletRequest request) {
        CurrentSessions.require(request);
        return ApiResponse.success(fleet.fleetStatus());
    }

    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------

    /** 默认确定性环形 route：(0,0)→(3,0)→(3,3)→(0,3)，每路点拍照。 */
    private List<Map<String, Object>> defaultPatrolRoute() {
        List<Map<String, Object>> route = new java.util.ArrayList<>();
        for (double theta : new double[]{0, 90, 180, 270}) {
            Map<String, Object> point = new java.util.LinkedHashMap<>();
            point.put("x", theta == 0 || theta == 270 ? 0.0 : 3.0);
            point.put("y", theta == 0 || theta == 90 ? 0.0 : 3.0);
            point.put("theta", theta);
            point.put("label", "路点-" + (theta == 0 ? "北" : theta == 90 ? "东" : theta == 180 ? "南" : "西"));
            point.put("actions", List.of("CAPTURE"));
            route.add(point);
        }
        return route;
    }

    /** 写操作门禁：登录 + admin.config 能力 + 审计留痕。 */
    private SessionUser requireConfigurator(HttpServletRequest request, String action, String target) {
        SessionUser user = CurrentSessions.require(request);
        if (!accounts.hasPlatformCapability(user, "admin.config")) {
            audit.record(user, action, target, "DENIED");
            throw new com.smartops.exception.BusinessException(403, "需要 admin.config 能力");
        }
        audit.record(user, action, target, "ALLOWED");
        return user;
    }
}
