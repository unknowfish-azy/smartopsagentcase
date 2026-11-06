package com.smartops.runbook;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.runbook.RunbookCatalogService.ParameterSpec;
import com.smartops.runbook.RunbookCatalogService.RunbookView;
import com.smartops.runbook.RunbookCatalogService.StepSpec;
import com.smartops.runbook.RunbookCatalogService.VersionDraft;
import com.smartops.runbook.RunbookCatalogService.VersionView;
import com.smartops.runbook.RunbookExecutionService.PlanResult;
import com.smartops.runbook.RunbookExecutionService.RunView;
import com.smartops.runbook.RunbookExecutionService.ScheduleView;
import com.smartops.runbook.RunbookExecutionService.TriggerView;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Runbook 与自动化作业接口。
 *
 * <p>治理顺序固定：定义 → 保存不可变版本 → 发布 → 计划（固定参数/目标/版本快照）
 * → 审批 → 带确认码执行 → 逐目标结果 / 回滚。任何一步都不会跳过前一步。</p>
 */
@RestController
@RequestMapping("/api/runbooks")
@RequiredArgsConstructor
public class RunbookController {

    private final RunbookCatalogService catalog;
    private final RunbookExecutionService execution;

    /* ── 定义与版本 ───────────────────────────────────────────────────── */

    @GetMapping
    public ApiResponse<List<RunbookView>> list(
            @CurrentUser Long userId) {
        return ApiResponse.success(catalog.list(userId));
    }

    @PostMapping
    public ApiResponse<RunbookView> create(
            @CurrentUser Long userId,
            @Valid @RequestBody CreateRunbookRequest request) {
        return ApiResponse.success(catalog.create(userId, request.name(), request.description(),
                request.environment(), request.riskLevel(), request.ownerId()));
    }

    @GetMapping("/{id}")
    public ApiResponse<RunbookView> detail(
            @CurrentUser Long userId,
            @PathVariable long id) {
        return ApiResponse.success(catalog.detail(userId, id));
    }

    @PutMapping("/{id}")
    public ApiResponse<RunbookView> update(
            @CurrentUser Long userId,
            @PathVariable long id,
            @RequestBody UpdateRunbookRequest request) {
        return ApiResponse.success(catalog.update(userId, id, request.name(), request.description(),
                request.environment(), request.riskLevel(), request.enabled()));
    }

    @PostMapping("/{id}/versions")
    public ApiResponse<VersionView> saveVersion(
            @CurrentUser Long userId,
            @PathVariable long id,
            @Valid @RequestBody SaveVersionRequest request) {
        return ApiResponse.success(catalog.saveVersion(userId, id, new VersionDraft(request.note(),
                request.parameters(), request.defaultRuntimeIds(), request.selectorNote(), request.timeoutSec(),
                request.retryLimit(), request.concurrencyLimit(), request.batchSize(), request.canarySize(),
                request.idempotencyRule(), request.steps())));
    }

    @GetMapping("/{id}/versions")
    public ApiResponse<List<VersionView>> versions(
            @CurrentUser Long userId,
            @PathVariable long id) {
        return ApiResponse.success(catalog.versions(userId, id));
    }

    @PostMapping("/{id}/publish")
    public ApiResponse<RunbookView> publish(
            @CurrentUser Long userId,
            @PathVariable long id) {
        return ApiResponse.success(catalog.publish(userId, id));
    }

    /* ── 计划 / 审批 / 执行 ───────────────────────────────────────────── */

    @PostMapping("/{id}/plan")
    public ApiResponse<PlanResult> plan(
            @CurrentUser Long userId,
            @PathVariable long id,
            @Valid @RequestBody PlanRequest request) {
        return ApiResponse.success(execution.plan(userId, id, request.runtimeIds(), request.parameters(),
                request.productionTarget()));
    }

    @PostMapping("/runs/{runId}/targets")
    public ApiResponse<PlanResult> attachTargets(
            @CurrentUser Long userId,
            @PathVariable long runId,
            @Valid @RequestBody PlanRequest request) {
        return ApiResponse.success(execution.attachTargets(userId, runId, request.runtimeIds(),
                request.parameters(), request.productionTarget()));
    }

    @GetMapping("/runs")
    public ApiResponse<List<RunView>> runs(
            @CurrentUser Long userId,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(execution.listRuns(userId, status, limit));
    }

    @GetMapping("/runs/{runId}")
    public ApiResponse<RunView> runDetail(
            @CurrentUser Long userId,
            @PathVariable long runId) {
        return ApiResponse.success(execution.detail(userId, runId));
    }

    @PostMapping("/runs/{runId}/approve")
    public ApiResponse<RunView> approve(
            @CurrentUser Long userId,
            @PathVariable long runId,
            @RequestBody(required = false) ApproveRequest request) {
        return ApiResponse.success(execution.approve(userId, runId, request == null ? null : request.note()));
    }

    @PostMapping("/runs/{runId}/execute")
    public ApiResponse<RunView> execute(
            @CurrentUser Long userId,
            @PathVariable long runId,
            @Valid @RequestBody ExecuteRequest request) {
        return ApiResponse.success(execution.execute(userId, runId, request.confirmationNonce()));
    }

    @PostMapping("/runs/{runId}/cancel")
    public ApiResponse<RunView> cancel(
            @CurrentUser Long userId,
            @PathVariable long runId) {
        return ApiResponse.success(execution.cancel(userId, runId));
    }

    @PostMapping("/runs/{runId}/rollback")
    public ApiResponse<RunView> rollback(
            @CurrentUser Long userId,
            @PathVariable long runId) {
        return ApiResponse.success(execution.rollback(userId, runId));
    }

    /* ── 定时与事件触发 ───────────────────────────────────────────────── */

    @PostMapping("/{id}/schedules")
    public ApiResponse<ScheduleView> createSchedule(
            @CurrentUser Long userId,
            @PathVariable long id,
            @Valid @RequestBody ScheduleRequest request) {
        return ApiResponse.success(execution.createSchedule(userId, id, request.cronExpr(),
                request.environment(), request.nextFireAt()));
    }

    @GetMapping("/schedules")
    public ApiResponse<List<ScheduleView>> schedules(
            @CurrentUser Long userId) {
        return ApiResponse.success(execution.listSchedules(userId));
    }

    @PostMapping("/schedules/{scheduleId}/rearm")
    public ApiResponse<ScheduleView> rearmSchedule(
            @CurrentUser Long userId,
            @PathVariable long scheduleId,
            @Valid @RequestBody RearmRequest request) {
        return ApiResponse.success(execution.rearmSchedule(userId, scheduleId, request.nextFireAt()));
    }

    @DeleteMapping("/schedules/{scheduleId}")
    public ApiResponse<Void> deleteSchedule(
            @CurrentUser Long userId,
            @PathVariable long scheduleId) {
        execution.deleteSchedule(userId, scheduleId);
        return ApiResponse.success(null);
    }

    @PostMapping("/{id}/triggers")
    public ApiResponse<TriggerView> bindTrigger(
            @CurrentUser Long userId,
            @PathVariable long id,
            @RequestBody(required = false) TriggerRequest request) {
        return ApiResponse.success(execution.bindAlertTrigger(userId, id,
                request == null ? null : request.minSeverity()));
    }

    @GetMapping("/triggers")
    public ApiResponse<List<TriggerView>> triggers(
            @CurrentUser Long userId) {
        return ApiResponse.success(execution.listTriggers(userId));
    }

    @DeleteMapping("/{id}/triggers/{eventType}")
    public ApiResponse<Void> deleteTrigger(
            @CurrentUser Long userId,
            @PathVariable long id,
            @PathVariable String eventType) {
        execution.deleteTrigger(userId, id, eventType);
        return ApiResponse.success(null);
    }

    /** 运维/测试用的手动触发端点：等价于后台扫描的一次执行，便于真实验证。 */
    @PostMapping("/automation/fire")
    public ApiResponse<Map<String, Integer>> fire(
            @RequestBody(required = false) FireRequest request) {
        int window = request == null || request.windowMinutes() == null ? 30 : request.windowMinutes();
        int limit = request == null || request.limit() == null ? 100 : request.limit();
        return ApiResponse.success(Map.of(
                "schedules", execution.fireDueSchedules(),
                "alerts", execution.fireAlertTriggers(window, limit)));
    }

    /* ── 请求体 ───────────────────────────────────────────────────────── */

    public record CreateRunbookRequest(@NotBlank String name, String description, String environment,
                                       String riskLevel, Long ownerId) {}

    public record UpdateRunbookRequest(String name, String description, String environment,
                                       String riskLevel, Boolean enabled) {}

    public record SaveVersionRequest(String note, List<ParameterSpec> parameters, List<String> defaultRuntimeIds,
                                     String selectorNote, Integer timeoutSec, Integer retryLimit,
                                     Integer concurrencyLimit, Integer batchSize, Integer canarySize,
                                     String idempotencyRule, @NotEmpty List<StepSpec> steps) {}

    public record PlanRequest(@NotEmpty List<String> runtimeIds, Map<String, String> parameters,
                              boolean productionTarget) {}

    public record ApproveRequest(String note) {}

    public record ExecuteRequest(@NotBlank String confirmationNonce) {}

    public record ScheduleRequest(@NotBlank String cronExpr, String environment, Instant nextFireAt) {}

    public record RearmRequest(@jakarta.validation.constraints.NotNull Instant nextFireAt) {}

    public record TriggerRequest(String minSeverity) {}

    public record FireRequest(Integer windowMinutes, Integer limit) {}
}
