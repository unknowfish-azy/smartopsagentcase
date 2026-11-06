package com.smartops.service;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRedactor;
import com.smartops.operations.OperationRiskPolicy;
import com.smartops.operations.OperationRuntimeRegistry;
import com.smartops.runbook.RunbookExecutionService;
import com.smartops.runbook.RunbookExecutionService.RunView;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.security.SecureRandom;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 多机批量命令。
 *
 * <p>PERF-04：执行不再把命令写进交互 shell 后直接返回 {@code SENT}，而是复用
 * {@link RunbookExecutionService} 的 Run + 目标子任务模型：一个有界并发（默认 10）
 * 的 Run、逐目标 SUCCEEDED/FAILED/UNKNOWN/CANCELLED、可取消，并且每个目标仍写
 * 权威的 {@code operation_run_record}。审批沿用本服务既有的预览 + 二次确认。</p>
 */
@Service
public class MultiExecService {
    private final OperationRuntimeRegistry registry;
    private final RunbookExecutionService runbookExecution;
    private final OperationRiskPolicy riskPolicy = new OperationRiskPolicy();
    private final SecureRandom random = new SecureRandom();
    private final Map<String, Preview> previews = new ConcurrentHashMap<>();
    private final Map<String, Long> activeRuns = new ConcurrentHashMap<>();
    private final int maxParallel;
    private final int timeoutMs;
    private final long previewTtlMs;
    private final int previewMaxEntries;

    public MultiExecService(OperationRuntimeRegistry registry, RunbookExecutionService runbookExecution,
                            @Value("${smartops.operations.multi-exec.max-parallel:10}") int maxParallel,
                            @Value("${smartops.operations.multi-exec.timeout-ms:120000}") int timeoutMs,
                            @Value("${smartops.operations.multi-exec.preview-ttl-ms:900000}") long previewTtlMs,
                            @Value("${smartops.operations.multi-exec.preview-max-entries:200}") int previewMaxEntries) {
        this.registry = registry;
        this.runbookExecution = runbookExecution;
        this.maxParallel = Math.max(1, Math.min(10, maxParallel));
        this.timeoutMs = Math.max(5_000, timeoutMs);
        this.previewTtlMs = Math.max(1, previewTtlMs);
        this.previewMaxEntries = Math.max(1, previewMaxEntries);
    }

    public Preview preview(Long userId, String command, List<String> runtimeIds, boolean productionTarget) {
        if (command == null || command.isBlank()) throw new BusinessException(400, "COMMAND_REQUIRED");
        if (runtimeIds == null || runtimeIds.isEmpty()) throw new BusinessException(400, "TARGETS_REQUIRED");
        List<String> immutableTargets = List.copyOf(runtimeIds);
        immutableTargets.forEach(id -> registry.requireOwned(id, userId));
        // SEC-03：预览必须绑定创建者并带 TTL/上限，防止内存堆积与过期预览被执行。
        purgeExpiredPreviews();
        if (previews.size() >= previewMaxEntries) throw new BusinessException(429, "PREVIEW_LIMIT_EXCEEDED");
        OperationRiskPolicy.Assessment assessment = riskPolicy.assess(command, immutableTargets.size() > 1, productionTarget);
        String id = UUID.randomUUID().toString();
        String nonce = nonce();
        Preview preview = new Preview(id, immutableTargets, OperationRedactor.redact(command), assessment.risk().name(),
                assessment.requiredApprovals(), nonce, productionTarget, command, userId, System.currentTimeMillis());
        previews.put(id, preview);
        return preview;
    }

    public ExecutionResult execute(Long userId, String previewId, String confirmationNonce, String secondConfirmationNonce) {
        Preview preview = previews.get(previewId);
        if (preview == null) throw new BusinessException(404, "PREVIEW_NOT_FOUND");
        if (System.currentTimeMillis() - preview.createdAt() > previewTtlMs) {
            previews.remove(previewId);
            throw new BusinessException(409, "PREVIEW_EXPIRED");
        }
        if (!preview.confirmationNonce().equals(confirmationNonce)) throw new BusinessException(409, "CONFIRMATION_REQUIRED");
        if (preview.requiredApprovals() > 1 && !preview.confirmationNonce().equals(secondConfirmationNonce)) {
            throw new BusinessException(409, "SECOND_CONFIRMATION_REQUIRED");
        }
        // SEC-03：双人确认必须来自不同主体——执行者等于预览创建者即自批，
        // 回显同一个 nonce 不构成第二人复核。
        if (preview.requiredApprovals() > 1 && preview.ownerId() != null && preview.ownerId().equals(userId)) {
            throw new BusinessException(409, "SECOND_APPROVER_REQUIRED");
        }
        if (previews.remove(previewId) == null) {
            throw new BusinessException(409, "MULTI_EXEC_PREVIEW_ALREADY_EXECUTED");
        }

        long runId;
        try {
            runId = runbookExecution.prepareAdHocBatch(userId, preview.id(), preview.rawCommand(),
                    preview.targetRuntimeIds(), preview.requiredApprovals(), preview.productionTarget(),
                    confirmationNonce, maxParallel, timeoutMs / 1000);
        } catch (RuntimeException failedBeforeRun) {
            // 计划阶段失败时尚未创建 Run，恢复预览以便修正后重试；
            // 一旦 Run 已创建，下面不再恢复预览，避免重复执行同一批命令。
            previews.put(previewId, preview);
            throw failedBeforeRun;
        }

        activeRuns.put(previewId, runId);
        try {
            RunView run = runbookExecution.execute(userId, runId, confirmationNonce);
            List<TargetResult> results = run.targets().stream()
                    .map(target -> new TargetResult(target.runtimeId(), target.status(), target.error(),
                            target.operationRunId(), target.exitCode(), target.outputExcerpt(),
                            target.dispatchStatus()))
                    .toList();
            List<String> unknown = results.stream()
                    .filter(result -> "UNKNOWN".equals(result.status())).map(TargetResult::runtimeId).toList();
            List<String> notDispatched = results.stream()
                    .filter(result -> "NOT_DISPATCHED".equals(result.dispatchStatus())
                            || ("CANCELLED".equals(result.status()) && result.dispatchStatus() == null))
                    .map(TargetResult::runtimeId).toList();
            return new ExecutionResult(preview.id(), runId, run.status(), run.succeeded(), run.failed(),
                    run.unknown(), run.cancelled(), results, unknown, notDispatched);
        } finally {
            activeRuns.remove(previewId);
        }
    }

    /** 取消正在执行的批量：只由 Runbook 统一的状态机决定，未命中不猜测为已取消。 */
    public CancelResult cancel(Long userId, String previewId) {
        Long runId = activeRuns.get(previewId);
        if (runId == null) return new CancelResult(previewId, false, null, "NOT_RUNNING");
        try {
            RunView run = runbookExecution.cancel(userId, runId);
            return new CancelResult(previewId, true, runId, run.status());
        } catch (BusinessException notCancellable) {
            if (notCancellable.getCode() == 409) {
                return new CancelResult(previewId, false, runId, "NOT_CANCELLABLE");
            }
            throw notCancellable;
        }
    }

    private String nonce() {
        byte[] bytes = new byte[18];
        random.nextBytes(bytes);
        return java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private void purgeExpiredPreviews() {
        long now = System.currentTimeMillis();
        previews.entrySet().removeIf(entry -> now - entry.getValue().createdAt() > previewTtlMs);
    }

    public record Preview(String id, List<String> targetRuntimeIds, String redactedCommand, String risk,
                          int requiredApprovals, String confirmationNonce, boolean productionTarget,
                          @JsonIgnore String rawCommand, @JsonIgnore Long ownerId, @JsonIgnore long createdAt) {}
    public record TargetResult(String runtimeId, String status, String error, Long operationRunId, Integer exitCode,
                               String outputExcerpt, String dispatchStatus) {}
    public record ExecutionResult(String previewId, long runId, String status, int succeeded, int failed,
                                  int unknown, int cancelled, List<TargetResult> results,
                                  List<String> unknownTargets, List<String> notDispatchedTargets) {}
    public record CancelResult(String previewId, boolean cancelled, Long runId, String status) {}
}
