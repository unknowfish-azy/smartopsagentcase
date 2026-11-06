package com.smartops.runbook;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRiskPolicy;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import com.smartops.runbook.RunbookCatalogService.ParameterSpec;
import com.smartops.runbook.RunbookCatalogService.RunbookRow;
import com.smartops.runbook.RunbookCatalogService.StepView;
import com.smartops.runbook.RunbookCatalogService.VersionView;
import com.smartops.runbook.RunbookEnums.Environment;
import com.smartops.runbook.RunbookEnums.OnFailure;
import com.smartops.runbook.RunbookEnums.Phase;
import com.smartops.runbook.RunbookEnums.Risk;
import com.smartops.runbook.RunbookEnums.RunStatus;
import com.smartops.runbook.RunbookEnums.TargetStatus;
import com.smartops.runbook.RunbookEnums.Trigger;
import com.smartops.sentinel.SentinelVariables;
import com.smartops.service.OperationRunRecorder;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * Runbook 执行编排：计划（审批对象快照）→ 审批 → 执行 → 逐目标结果 / 回滚。
 *
 * <p><b>为什么不新建第二条执行通路</b>：命令执行仍走
 * {@link OperationRuntime#execute}，证据仍由 {@link OperationRunRecorder}
 * 写入权威的 {@code operation_run_record}（每个目标每次尝试一条 Run）。
 * 本类只增加"作业级编排"：前置检查 → 执行 → 后置检查、批次/金丝雀、
 * 失败分支与回滚。它不新建运行记录、权限或审计体系。</p>
 *
 * <p><b>审批一致性</b>：计划时把 版本 + 参数 + 目标快照 + 步骤正文 生成内容哈希；
 * 执行前重新计算并比对，不一致直接拒绝（{@code RUNBOOK_CONTENT_DRIFT}），
 * 因此"批准的"和"执行的"不可能不是同一份内容。</p>
 *
 * <p><b>状态口径</b>：{@code UNKNOWN} 表示命令已派发但结果不可确认，
 * 禁止自动重试写操作；{@code TIMEOUT} 表示预算耗尽且尚未派发任何写命令。</p>
 */
@Service
public class RunbookExecutionService {

    private static final int MAX_PARALLEL = 10;
    private static final int MAX_OUTPUT_CHARS = 20_000;
    private static final long LEASE_MS = 60_000L;
    private static final int MAX_OUTPUT_BYTES = 512 * 1024;
    /**
     * 多机批量命令的内部 Runbook 名称前缀。PERF-04 让批量命令复用同一套
     * Run / 目标子任务模型，而不是另建一条"只发送不确认"的执行通路。
     */
    static final String AD_HOC_RUNBOOK_PREFIX = "__multi_exec__";

    private final JdbcTemplate jdbc;
    private final OperationRuntimeRegistry registry;
    private final OperationRunRecorder runRecorder;
    private final RunbookCatalogService catalog;
    private final OperationRiskPolicy riskPolicy = new OperationRiskPolicy();

    public RunbookExecutionService(JdbcTemplate jdbc, OperationRuntimeRegistry registry,
                                   OperationRunRecorder runRecorder, RunbookCatalogService catalog) {
        this.jdbc = jdbc;
        this.registry = registry;
        this.runRecorder = runRecorder;
        this.catalog = catalog;
    }

    /* ── 计划 ─────────────────────────────────────────────────────────── */

    /**
     * 手动计划：解析参数、固定目标快照、按风险计算所需审批次数。
     *
     * @return 预览命令 + 确认码；低风险作业可直接执行，其它作业需先审批
     */
    @Transactional
    public PlanResult plan(Long userId, long runbookId, List<String> runtimeIds, Map<String, String> parameters,
                           boolean productionTarget) {
        RunbookRow runbook = catalog.requireRunbook(userId, runbookId);
        if (!runbook.enabled()) throw new BusinessException(409, "RUNBOOK_DISABLED");
        if (runbook.currentVersion() == null) throw new BusinessException(409, "RUNBOOK_VERSION_REQUIRED");
        VersionView version = catalog.loadVersion(runbookId, runbook.currentVersion());

        long runId = insertRunSkeleton(userId, runbook, version, Trigger.MANUAL, null, null,
                RunStatus.AWAITING_TARGETS);
        return applyPlan(userId, runId, runbook, version, runtimeIds, parameters, productionTarget);
    }

    /**
     * 定时 / 事件触发的作业：先落一条"等待绑定目标"的运行。
     *
     * <p>运行连接是会话级资源，后台线程无法凭空获得目标；因此触发只负责
     * 生成待绑定作业，不允许把"没有目标"伪装成"执行完成"。</p>
     */
    @Transactional
    public long createTriggeredRun(Long userId, long runbookId, Trigger trigger, String triggerRef,
                                   String idempotencyKey) {
        RunbookRow runbook = catalog.requireRunbook(userId, runbookId);
        if (!runbook.enabled() || runbook.currentVersion() == null) {
            throw new BusinessException(409, "RUNBOOK_NOT_PUBLISHED");
        }
        VersionView version = catalog.loadVersion(runbookId, runbook.currentVersion());
        if (idempotencyKey != null) {
            Integer existing = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM runbook_run WHERE user_id=? AND idempotency_key=?",
                    Integer.class, userId, idempotencyKey);
            if (existing != null && existing > 0) return 0L;
        }
        try {
            return insertRunSkeleton(userId, runbook, version, trigger, triggerRef, idempotencyKey,
                    RunStatus.AWAITING_TARGETS);
        } catch (DuplicateKeyException raced) {
            // 并发轮询同时触发同一事件：唯一索引兜底，只保留一条。
            return 0L;
        }
    }

    /** 为"等待绑定目标"的作业补上目标与参数，进入审批或可直接执行。 */
    @Transactional
    public PlanResult attachTargets(Long userId, long runId, List<String> runtimeIds,
                                    Map<String, String> parameters, boolean productionTarget) {
        RunRow run = loadRun(userId, runId);
        if (!RunStatus.AWAITING_TARGETS.name().equals(run.status())) {
            throw new BusinessException(409, "RUNBOOK_RUN_TARGETS_ALREADY_ATTACHED");
        }
        RunbookRow runbook = catalog.requireRunbook(userId, run.runbookId());
        VersionView version = catalog.loadVersion(run.runbookId(), run.version());
        return applyPlan(userId, runId, runbook, version, runtimeIds, parameters, productionTarget);
    }

    /**
     * PERF-04：把多机批量命令固化为一次 Runbook Run。
     *
     * <p>与 OPS-11 使用同一套实现：一个 Run、逐目标子任务、同一 operation_run_record
     * 证据、同一取消/并发/状态口径。审批由调用方（multi-exec 预览 + 二次确认）完成，
     * 这里只校验审批次数与执行期风险一致，然后把运行置为 APPROVED。</p>
     *
     * @return 已就绪、可带 {@code confirmationNonce} 执行的 runId
     */
    @Transactional
    public long prepareAdHocBatch(Long userId, String batchId, String command, List<String> runtimeIds,
                                  int expectedApprovals, boolean productionTarget, String confirmationNonce,
                                  int maxParallel, int timeoutSec) {
        if (batchId == null || batchId.isBlank()) throw new BusinessException(400, "MULTI_EXEC_BATCH_REQUIRED");
        if (command == null || command.isBlank()) throw new BusinessException(400, "MULTI_EXEC_COMMAND_REQUIRED");
        if (confirmationNonce == null || confirmationNonce.isBlank()) {
            throw new BusinessException(409, "MULTI_EXEC_CONFIRMATION_REQUIRED");
        }
        List<String> targets = normalizeTargets(userId, runtimeIds);
        RunbookRow runbook = ensureAdHocRunbook(userId, productionTarget);
        VersionView version = createAdHocVersion(userId, runbook, command, targets.size(), maxParallel, timeoutSec);
        long runId = insertRunSkeleton(userId, runbook, version, Trigger.MANUAL, batchId,
                "multi-exec:" + batchId, RunStatus.AWAITING_TARGETS);
        PlanResult planned = applyPlan(userId, runId, runbook, version, targets, Map.of(), productionTarget);
        if (planned.requiredApprovals() != expectedApprovals) {
            throw new BusinessException(409, "MULTI_EXEC_APPROVAL_DRIFT");
        }
        int approved = jdbc.update("""
                UPDATE runbook_run SET status='APPROVED',approval_count=?,approved_at=?,approved_by=NULL,
                       second_approver_id=NULL,nonce_hash=?
                 WHERE id=? AND user_id=?
                """, expectedApprovals, Timestamp.from(Instant.now()), RunbookSupport.sha256(confirmationNonce.trim()),
                runId, userId);
        if (approved == 0) throw new BusinessException(404, "RUNBOOK_RUN_NOT_FOUND");
        return runId;
    }

    private RunbookRow ensureAdHocRunbook(Long userId, boolean productionTarget) {
        String name = AD_HOC_RUNBOOK_PREFIX + (productionTarget ? "prod" : "dev");
        List<RunbookRow> existing = jdbc.query("""
                SELECT id,user_id,name,description,environment,owner_id,declared_risk,enabled,current_version,
                       created_at,updated_at
                  FROM runbook WHERE user_id=? AND name=?
                """, this::mapRunbookRow, userId, name);
        if (!existing.isEmpty()) return existing.get(0);
        try {
            jdbc.update("""
                    INSERT INTO runbook(user_id,name,description,environment,owner_id,declared_risk,enabled)
                    VALUES(?,?,?,?,?,?,0)
                    """, userId, name, "系统内部：多机批量命令，复用 Runbook 目标子任务模型",
                    productionTarget ? "PROD" : "DEV", userId, Risk.LOW.name());
        } catch (DuplicateKeyException raced) {
            // 并发首次使用：唯一索引兜底，下面重查即可。
        }
        List<RunbookRow> rows = jdbc.query("""
                SELECT id,user_id,name,description,environment,owner_id,declared_risk,enabled,current_version,
                       created_at,updated_at
                  FROM runbook WHERE user_id=? AND name=?
                """, this::mapRunbookRow, userId, name);
        if (rows.isEmpty()) throw new BusinessException(500, "MULTI_EXEC_RUNBOOK_INIT_FAILED");
        return rows.get(0);
    }

    private VersionView createAdHocVersion(Long userId, RunbookRow runbook, String command, int targetCount,
                                           int maxParallel, int timeoutSec) {
        OperationRiskPolicy.Risk assessedRisk = riskPolicy.assess(command, targetCount > 1,
                Environment.of(runbook.environment()).production()).risk();
        String riskName = assessedRisk.name();
        int concurrency = Math.max(1, Math.min(MAX_PARALLEL, maxParallel));
        int timeout = Math.max(5, Math.min(86_400, timeoutSec));
        int batchSize = Math.max(1, Math.min(100, targetCount));
        for (int attempt = 0; attempt < 2; attempt++) {
            try {
                Integer latest = jdbc.queryForObject(
                        "SELECT COALESCE(MAX(version),0) FROM runbook_version WHERE runbook_id=?",
                        Integer.class, runbook.id());
                int versionNo = (latest == null ? 0 : latest) + 1;
                KeyHolder keys = new GeneratedKeyHolder();
                jdbc.update(connection -> {
                    PreparedStatement statement = connection.prepareStatement("""
                            INSERT INTO runbook_version(runbook_id,version,note,risk_level,parameters_json,
                                selector_json,timeout_sec,retry_limit,concurrency_limit,batch_size,canary_size,
                                idempotency_rule,created_by)
                            VALUES(?,?,?,?,NULL,NULL,?,0,?,?,0,?,?)
                            """, Statement.RETURN_GENERATED_KEYS);
                    statement.setLong(1, runbook.id());
                    statement.setInt(2, versionNo);
                    statement.setString(3, "多机批量命令：版本正文即命令原文，单目标一次");
                    statement.setString(4, riskName);
                    statement.setInt(5, timeout);
                    statement.setInt(6, concurrency);
                    statement.setInt(7, batchSize);
                    statement.setString(8, "同一批号+目标只执行一次，不自动重试写操作");
                    statement.setLong(9, userId);
                    return statement;
                }, keys);
                long versionId = generatedId(keys);
                jdbc.update("""
                        INSERT INTO runbook_step(version_id,phase,seq,name,body,expect_exit_code,on_failure)
                        VALUES(?, 'EXECUTE', 1, '多机批量命令', ?, 0, 'ABORT')
                        """, versionId, command);
                jdbc.update("UPDATE runbook SET current_version=?,declared_risk=?,updated_at=? WHERE id=?",
                        versionNo, riskName, Timestamp.from(Instant.now()), runbook.id());
                return catalog.loadVersion(runbook.id(), versionNo);
            } catch (DuplicateKeyException raced) {
                if (attempt == 1) throw new BusinessException(409, "MULTI_EXEC_VERSION_CONFLICT");
            }
        }
        throw new BusinessException(409, "MULTI_EXEC_VERSION_CONFLICT");
    }

    private RunbookRow mapRunbookRow(java.sql.ResultSet result, int ignored) throws java.sql.SQLException {
        return new RunbookRow(result.getLong("id"), result.getLong("user_id"), result.getString("name"),
                result.getString("description"), result.getString("environment"),
                (Long) result.getObject("owner_id"), result.getString("declared_risk"), result.getBoolean("enabled"),
                (Integer) result.getObject("current_version"), instant(result.getTimestamp("created_at")),
                instant(result.getTimestamp("updated_at")));
    }

    private static boolean isAdHoc(RunbookRow runbook) {
        return runbook != null && runbook.name() != null && runbook.name().startsWith(AD_HOC_RUNBOOK_PREFIX);
    }

    private static List<StepPreview> rawStepPreviews(List<StepView> steps) {
        return steps.stream().map(step -> new StepPreview(step.phase(), step.seq(), step.name(), step.body())).toList();
    }

    private PlanResult applyPlan(Long userId, long runId, RunbookRow runbook, VersionView version,
                                 List<String> runtimeIds, Map<String, String> parameters, boolean productionTarget) {
        List<String> targets = normalizeTargets(userId, runtimeIds);
        Map<String, String> params = resolveParameters(version.parameters(), parameters);
        List<StepPreview> previews = isAdHoc(runbook)
                ? rawStepPreviews(version.steps())
                : renderSteps(version.steps(), params);
        Environment environment = Environment.of(runbook.environment());
        boolean production = environment.production() || productionTarget;

        String executeBodies = version.steps().stream()
                .filter(step -> Phase.EXECUTE.name().equals(step.phase()))
                .map(StepView::body).reduce("", (left, right) -> left + "\n" + right);
        OperationRiskPolicy.Assessment assessment = riskPolicy.assess(executeBodies, targets.size() > 1, production);
        Risk risk = Risk.max(Risk.of(version.riskLevel()), Risk.of(assessment.risk().name()));
        int approvals = assessment.requiredApprovals();
        if (environment.production() && risk != Risk.LOW) approvals = Math.max(approvals, 1);
        if (production && targets.size() > 1) approvals = Math.max(approvals, 2);

        String hash = expectedContentHash(version, params, targets);
        String nonce = RunbookSupport.nonce();
        String nonceHash = RunbookSupport.sha256(nonce);
        RunStatus status = approvals == 0 ? RunStatus.APPROVED : RunStatus.PENDING_APPROVAL;

        jdbc.update("""
                UPDATE runbook_run SET status=?,parameters_json=?,target_selector_json=?,target_snapshot_json=?,
                       content_hash=?,risk_level=?,required_approvals=?,approval_count=0,approved_by=NULL,
                       second_approver_id=NULL,approved_at=NULL,nonce_hash=?,total_targets=?,
                       succeeded_count=0,failed_count=0,unknown_count=0,cancelled_count=0,skipped_count=0
                 WHERE id=? AND user_id=?
                """, status.name(), RunbookSupport.toJson(params), RunbookSupport.toJson(selector(targets)),
                RunbookSupport.toJson(targets), hash, risk.name(), approvals, nonceHash, targets.size(), runId, userId);

        int canarySize = Math.min(version.canarySize(), targets.size());
        for (int index = 0; index < targets.size(); index++) {
            boolean canary = index < canarySize;
            int batchNo = canary ? 0 : ((index - canarySize) / version.batchSize()) + 1;
            insertTarget(runId, targets.get(index), batchNo, canary);
        }
        return new PlanResult(runId, status.name(), risk.name(), approvals, nonce, hash, targets, previews,
                status == RunStatus.APPROVED
                        ? "低风险作业无需他人审批；请带确认码提交执行。"
                        : "请由其他有审批权的成员审批后再提交确认码执行。",
                "计划已固定版本 " + version.version() + "、参数与目标快照；执行前会校验内容哈希。");
    }

    /* ── 审批 ─────────────────────────────────────────────────────────── */

    /**
     * 审批人与发起人可以是不同用户，因此这里按 runId 读取，而不按"当前用户拥有"过滤。
     * 其余动作（执行 / 取消 / 回滚）仍然只允许发起人本人操作。
     */
    @Transactional
    public RunView approve(Long userId, long runId, String note) {
        RunRow run = loadRunById(runId);
        if (!RunStatus.PENDING_APPROVAL.name().equals(run.status())) {
            throw new BusinessException(409, "RUNBOOK_RUN_NOT_PENDING_APPROVAL");
        }
        if (userId.equals(run.userId())) throw new BusinessException(409, "RUNBOOK_SELF_APPROVAL_FORBIDDEN");
        if (run.approvedBy() == null) {
            jdbc.update("UPDATE runbook_run SET approved_by=?,approval_count=approval_count+1 WHERE id=?",
                    userId, runId);
        } else if (run.secondApproverId() == null && run.requiredApprovals() > 1) {
            if (userId.equals(run.approvedBy())) throw new BusinessException(409, "RUNBOOK_APPROVER_DUPLICATED");
            jdbc.update("UPDATE runbook_run SET second_approver_id=?,approval_count=approval_count+1 WHERE id=?",
                    userId, runId);
        } else {
            throw new BusinessException(409, "RUNBOOK_APPROVAL_ALREADY_COMPLETE");
        }
        int count = run.approvalCount() + 1;
        boolean complete = count >= run.requiredApprovals();
        jdbc.update("UPDATE runbook_run SET status=?,approved_at=?,note=? WHERE id=?",
                complete ? RunStatus.APPROVED.name() : RunStatus.PENDING_APPROVAL.name(),
                Timestamp.from(Instant.now()), RunbookSupport.truncate(note, 500), runId);
        return detail(run.userId(), runId);
    }

    /* ── 执行 ─────────────────────────────────────────────────────────── */

    public RunView execute(Long userId, long runId, String confirmationNonce) {
        RunRow run = loadRun(userId, runId);
        if (!RunStatus.APPROVED.name().equals(run.status())) {
            throw new BusinessException(409, "RUNBOOK_RUN_NOT_APPROVED");
        }
        if (run.cancelRequested()) throw new BusinessException(409, "RUNBOOK_RUN_CANCELLED");
        if (confirmationNonce == null || run.nonceHash() == null
                || !RunbookSupport.sha256(confirmationNonce.trim()).equals(run.nonceHash())) {
            throw new BusinessException(409, "RUNBOOK_CONFIRMATION_REQUIRED");
        }
        RunbookRow runbook = catalog.requireRunbook(userId, run.runbookId());
        VersionView version = catalog.loadVersion(run.runbookId(), run.version());
        Map<String, String> params = RunbookSupport.readStringMap(run.parametersJson());
        List<String> targets = RunbookSupport.readStringList(run.targetSnapshotJson());
        if (!expectedContentHash(version, params, targets).equals(run.contentHash())) {
            throw new BusinessException(409, "RUNBOOK_CONTENT_DRIFT");
        }

        Instant startedAt = Instant.now();
        int claimed = jdbc.update("""
                UPDATE runbook_run SET status='RUNNING',started_at=?,finished_at=NULL
                 WHERE id=? AND user_id=? AND status='APPROVED'
                """, Timestamp.from(startedAt), runId, userId);
        if (claimed == 0) throw new BusinessException(409, "RUNBOOK_RUN_NOT_APPROVED");

        List<TargetRow> targetRows = loadTargets(runId);
        List<TargetOutcome> outcomes = new ArrayList<>();
        executeGroups(userId, run, runbook, version, params, targetRows, outcomes);
        finishRun(runId);
        return detail(userId, runId);
    }

    /** 批次 / 金丝雀：先跑金丝雀，金丝雀不是全成功就不放量。 */
    private void executeGroups(Long userId, RunRow run, RunbookRow runbook, VersionView version,
                               Map<String, String> params, List<TargetRow> targetRows,
                               List<TargetOutcome> outcomes) {
        List<TargetRow> canary = targetRows.stream().filter(TargetRow::canary).toList();
        int concurrency = Math.max(1, Math.min(version.concurrencyLimit(), MAX_PARALLEL));

        if (!canary.isEmpty()) {
            outcomes.addAll(runGroup(userId, run, runbook, version, params, canary, concurrency));
            boolean allGood = outcomes.stream().allMatch(outcome -> outcome.status() == TargetStatus.SUCCEEDED);
            if (!allGood) {
                List<TargetRow> rest = targetRows.stream().filter(target -> !target.canary()).toList();
                for (TargetRow target : rest) {
                    markSkipped(run.id(), target.runtimeId(), "金丝雀批次未全部成功，本批次未放量");
                    outcomes.add(new TargetOutcome(target.runtimeId(), TargetStatus.SKIPPED,
                            "金丝雀批次未全部成功，本批次未放量", null, null, null, null, null, 0));
                }
                return;
            }
        }

        List<TargetRow> rest = targetRows.stream().filter(target -> !target.canary()).toList();
        if (rest.isEmpty()) return;
        List<List<TargetRow>> batches = new ArrayList<>();
        List<TargetRow> current = new ArrayList<>();
        for (TargetRow target : rest) {
            if (current.size() >= version.batchSize()) {
                batches.add(current);
                current = new ArrayList<>();
            }
            current.add(target);
        }
        if (!current.isEmpty()) batches.add(current);

        for (List<TargetRow> batch : batches) {
            outcomes.addAll(runGroup(userId, run, runbook, version, params, batch, concurrency));
            if (cancelRequestedNow(run.id())) break;
        }
    }

    private List<TargetOutcome> runGroup(Long userId, RunRow run, RunbookRow runbook, VersionView version,
                                         Map<String, String> params, List<TargetRow> group, int concurrency) {
        if (group.isEmpty()) return List.of();
        ExecutorService pool = Executors.newFixedThreadPool(Math.min(concurrency, group.size()));
        try {
            List<Future<TargetOutcome>> futures = new ArrayList<>();
            for (TargetRow target : group) {
                futures.add(pool.submit(() -> runTargetWithRetry(userId, run, runbook, version, params, target)));
            }
            List<TargetOutcome> outcomes = new ArrayList<>();
            for (Future<TargetOutcome> future : futures) {
                try {
                    outcomes.add(future.get());
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    outcomes.add(new TargetOutcome("unknown", TargetStatus.FAILED,
                            "执行线程被中断，结果未知", null, null, null, null, null, 0));
                    break;
                } catch (ExecutionException failure) {
                    outcomes.add(new TargetOutcome("unknown", TargetStatus.FAILED,
                            "执行线程异常：" + safeMessage(failure.getCause()), null, null, null, null, null, 0));
                }
            }
            return outcomes;
        } finally {
            pool.shutdownNow();
        }
    }

    private TargetOutcome runTargetWithRetry(Long userId, RunRow run, RunbookRow runbook, VersionView version,
                                             Map<String, String> params, TargetRow target) {
        TargetOutcome outcome = null;
        for (int attempt = 0; attempt <= version.retryLimit(); attempt++) {
            try {
                outcome = runTargetAttempt(userId, run, runbook, version, params, target, attempt);
            } catch (RuntimeException broken) {
                // 编排异常可能发生在命令派发之后：远端是否生效不确定，按 UNKNOWN 处理，
                // 既不能静默当成功，也不能当可安全重试的失败。
                String error = "作业编排异常，远端状态需人工核验：" + safeMessage(broken);
                finishTarget(run.id(), target.runtimeId(), TargetStatus.UNKNOWN, attempt + 1, null, null,
                        "", error, null, null, null, null, Instant.now(), null, null, null, null);
                outcome = new TargetOutcome(target.runtimeId(), TargetStatus.UNKNOWN, error, null, null,
                        "", null, null, attempt + 1);
            }
            // UNKNOWN 时远端可能已经生效，绝不自动重试写操作；CANCELLED / TIMEOUT 也不重试。
            if (outcome.status() == TargetStatus.UNKNOWN || outcome.status() == TargetStatus.CANCELLED
                    || outcome.status() == TargetStatus.TIMEOUT) break;
        }
        return outcome;
    }

    private TargetOutcome runTargetAttempt(Long userId, RunRow run, RunbookRow runbook, VersionView version,
                                           Map<String, String> params, TargetRow target, int attempt) {
        Instant startedAt = Instant.now();
        int attemptNo = attempt + 1;
        if (!markRunning(run.id(), target.runtimeId(), attemptNo, startedAt)) {
            return new TargetOutcome(target.runtimeId(), TargetStatus.CANCELLED, "作业已取消，该目标未派发",
                    null, null, "", null, null, attemptNo);
        }

        OperationRuntime runtime;
        try {
            runtime = registry.requireOwned(target.runtimeId(), userId);
        } catch (RuntimeException unavailable) {
            String error = "运行连接不可用：" + safeMessage(unavailable);
            finishTarget(run.id(), target.runtimeId(), TargetStatus.FAILED, attemptNo, null, null,
                    "", error, null, null, null, null, startedAt, "NOT_DISPATCHED", null, null, null);
            return new TargetOutcome(target.runtimeId(), TargetStatus.FAILED, error, null, null,
                    "", null, null, attemptNo);
        }
        if (!runtime.isOpen()) {
            String error = "运行连接已关闭，未派发任何命令";
            finishTarget(run.id(), target.runtimeId(), TargetStatus.FAILED, attemptNo, null, null,
                    "", error, null, null, null, null, startedAt, "NOT_DISPATCHED", null, null, null);
            return new TargetOutcome(target.runtimeId(), TargetStatus.FAILED, error, null, null,
                    "", null, null, attemptNo);
        }

        Instant deadline = (run.startedAt() == null ? startedAt : run.startedAt())
                .plusSeconds(Math.max(5, version.timeoutSec()));
        String idempotencyKey = "runbook:" + run.id() + ":" + target.runtimeId() + ":a" + attemptNo;
        OperationRunRecorder.RunHandle handle;
        try {
            handle = runRecorder.start(new OperationRunRecorder.RunSpec(
                    UUID.randomUUID().toString(), userId, runtime, "runbook:" + runbook.id(),
                    idempotencyKey, startedAt, deadline, MAX_OUTPUT_BYTES, LEASE_MS));
        } catch (RuntimeException conflict) {
            String error = "目标本次尝试已存在执行记录（幂等键冲突），不重复派发：" + safeMessage(conflict);
            finishTarget(run.id(), target.runtimeId(), TargetStatus.FAILED, attemptNo, null, null,
                    "", error, null, null, null, null, startedAt, "NOT_DISPATCHED", null, null, null);
            return new TargetOutcome(target.runtimeId(), TargetStatus.FAILED, error, null, null,
                    "", null, null, attemptNo);
        }

        ExecutionState state = new ExecutionState();
        boolean executeRan = false;
        boolean rawCommand = isAdHoc(runbook);
        // 同一 Run 内的命令序号必须连续：operation_run_output 有 (run_id, sequence_no) 唯一约束。
        SequenceCounter sequence = new SequenceCounter();
        runPhase(Phase.PRE_CHECK, version.steps(), params, runtime, handle, deadline, run.id(), state, sequence, rawCommand);
        String preCheckStatus = phaseStatus(state);

        if (!state.failed && !state.cancelled && !state.timedOut && !state.uncertain) {
            executeRan = true;
            runPhase(Phase.EXECUTE, version.steps(), params, runtime, handle, deadline, run.id(), state, sequence, rawCommand);
        }
        if (!state.failed && !state.cancelled && !state.timedOut && !state.uncertain) {
            runPhase(Phase.POST_CHECK, version.steps(), params, runtime, handle, deadline, run.id(), state, sequence, rawCommand);
        }

        TargetStatus status;
        if (state.cancelled) {
            status = TargetStatus.CANCELLED;
        } else if (state.uncertain) {
            status = TargetStatus.UNKNOWN;
        } else if (state.timedOut) {
            status = state.dispatched ? TargetStatus.UNKNOWN : TargetStatus.TIMEOUT;
        } else if (state.failed || state.continuedFailure) {
            status = TargetStatus.FAILED;
        } else {
            status = TargetStatus.SUCCEEDED;
        }

        String postCheckStatus = Phase.POST_CHECK.name().equals(state.failedPhase)
                ? "FAILED" : (status == TargetStatus.SUCCEEDED ? "SUCCEEDED" : null);
        // 三个时间点分别落库：派发、执行阶段结束、后置验证通过。空值表示"未发生/未知"，
        // 不允许用最终成功反推派发时间。
        Instant executedAt = executeRan ? Instant.now() : null;
        Instant verifiedAt = "SUCCEEDED".equals(postCheckStatus) ? Instant.now() : null;
        String dispatchStatus = state.dispatched ? "SENT" : "NOT_DISPATCHED";
        String rollbackStatus = null;
        String rollbackOutput = null;
        if (state.failed && OnFailure.ROLLBACK.name().equals(state.onFailure)) {
            ExecutionState rollback = new ExecutionState();
            runPhase(Phase.ROLLBACK, version.steps(), params, runtime, handle, Instant.now().plusSeconds(300),
                    run.id(), rollback, sequence, false);
            rollbackStatus = rollback.failed ? TargetStatus.ROLLBACK_FAILED.name() : TargetStatus.ROLLED_BACK.name();
            rollbackOutput = rollback.output;
            status = rollback.failed ? TargetStatus.ROLLBACK_FAILED : TargetStatus.ROLLED_BACK;
            runRecorder.recordEvidence(handle, "RUNBOOK_ROLLBACK",
                    "失败分支=ROLLBACK；回滚结果=" + rollbackStatus + (rollback.error == null ? "" : ("；" + rollback.error)));
        }

        String recorderStatus = switch (status) {
            case SUCCEEDED -> "SUCCEEDED";
            case UNKNOWN -> "UNCERTAIN";
            case TIMEOUT -> "TIMEOUT";
            case CANCELLED -> "CANCELLED";
            default -> "FAILED";
        };
        runRecorder.finish(handle, recorderStatus, Instant.now());
        finishTarget(run.id(), target.runtimeId(), status, attemptNo, handle.id(),
                state.lastExitCode, state.output, state.error, preCheckStatus, postCheckStatus,
                rollbackStatus, rollbackOutput, startedAt, dispatchStatus, state.dispatchedAt,
                executedAt, verifiedAt);
        return new TargetOutcome(target.runtimeId(), status, state.error, handle.id(), state.lastExitCode,
                state.output, preCheckStatus, state.failedPhase == null && state.error == null
                ? null : state.failedPhase, attemptNo);
    }

    /** 执行一个阶段的步骤；状态累积到 {@code state}，一旦失败/取消/超时立即停止该阶段。 */
    private void runPhase(Phase phase, List<StepView> steps, Map<String, String> params, OperationRuntime runtime,
                          OperationRunRecorder.RunHandle handle, Instant deadline, long runId, ExecutionState state,
                          SequenceCounter sequence, boolean rawCommand) {
        List<StepView> phaseSteps = steps.stream()
                .filter(step -> phase.name().equals(step.phase())).toList();
        for (StepView step : phaseSteps) {
            if (cancelRequestedNow(runId)) {
                state.cancelled = true;
                state.error = "操作者在步骤之间请求取消；后续步骤未派发";
                return;
            }
            long remainingMs = deadline.toEpochMilli() - System.currentTimeMillis();
            if (remainingMs <= 0) {
                state.timedOut = true;
                state.error = "作业预算耗尽；步骤「" + step.name() + "」及后续步骤未派发";
                return;
            }
            SentinelVariables.Result substituted;
            String command;
            if (rawCommand) {
                // 多机批量命令按原样交给 shell：${HOME} 等是远端 shell 变量，
                // 不能让本地参数替换规则把它们判成"未提供的参数"。
                command = step.body();
            } else {
                try {
                    substituted = SentinelVariables.applyChecked(step.body(), params);
                } catch (IllegalArgumentException unsafe) {
                    state.failed = true;
                    state.failedPhase = phase.name();
                    state.onFailure = step.onFailure();
                    state.error = "参数值不安全：" + unsafe.getMessage();
                    return;
                }
                if (!substituted.unresolved().isEmpty()) {
                    state.failed = true;
                    state.failedPhase = phase.name();
                    state.onFailure = step.onFailure();
                    state.error = "步骤引用了未提供的参数：" + String.join("、", substituted.unresolved());
                    return;
                }
                command = substituted.body();
            }

            long stepTimeoutMs = step.timeoutSec() == null ? remainingMs
                    : Math.min(step.timeoutSec() * 1000L, remainingMs);
            sequence.value++;
            Instant commandStartedAt = Instant.now();
            try {
                if (Phase.EXECUTE.name().equals(phase.name()) && !state.dispatched) {
                    state.dispatched = true;
                    state.dispatchedAt = commandStartedAt;
                }
                OperationRuntime.CommandResult result = runtime.execute(command, Math.max(1, stepTimeoutMs));
                Instant commandEndedAt = Instant.now();
                String stdout = bound(result.stdout());
                String stderr = bound(result.stderr());
                state.lastExitCode = result.exitCode();
                state.output = RunbookSupport.excerpt((stdout + "\n" + stderr).strip());
                runRecorder.recordCommand(handle, sequence.value, command, result.exitCode(), stdout, stderr,
                        commandStartedAt, commandEndedAt,
                        truncated(result.stdout(), result.stderr()) || result.truncated());
                runRecorder.heartbeat(handle);
                if (result.exitCode() != step.expectExitCode()) {
                    state.failed = true;
                    state.failedPhase = phase.name();
                    state.onFailure = step.onFailure();
                    state.error = "步骤「" + step.name() + "」退出码 " + result.exitCode()
                            + "（期望 " + step.expectExitCode() + "）";
                    state.output = RunbookSupport.excerpt(stderr.isBlank() ? stdout : stderr);
                    if (OnFailure.CONTINUE.name().equals(step.onFailure())
                            && Phase.EXECUTE.name().equals(phase.name())) {
                        // CONTINUE 只对执行阶段生效：继续后续步骤，但整体仍记录为失败。
                        state.failed = false;
                        state.continuedFailure = true;
                        state.error = state.error + "；已按 CONTINUE 继续后续步骤";
                        continue;
                    }
                    return;
                }
            } catch (IOException failure) {
                Instant commandEndedAt = Instant.now();
                String error = safeMessage(failure);
                boolean timeout = "COMMAND_TIMEOUT".equals(failure.getMessage());
                runRecorder.recordCommand(handle, sequence.value, command, -1, "", error,
                        commandStartedAt, commandEndedAt, false);
                if (timeout && Phase.EXECUTE.name().equals(phase.name())) {
                    // 写命令可能已在远端开始：结果未知，不能当失败直接重试。
                    state.uncertain = true;
                    state.error = "步骤「" + step.name() + "」执行超时，远端是否生效未知";
                    return;
                }
                state.failed = true;
                state.failedPhase = phase.name();
                state.onFailure = step.onFailure();
                state.error = "步骤「" + step.name() + "」执行失败：" + error;
                return;
            }
        }
    }

    /* ── 取消 / 回滚 ─────────────────────────────────────────────────── */

    @Transactional
    public RunView cancel(Long userId, long runId) {
        RunRow run = loadRun(userId, runId);
        if (RunStatus.valueOf(run.status()).terminal()) {
            throw new BusinessException(409, "RUNBOOK_RUN_NOT_CANCELLABLE");
        }
        if (RunStatus.RUNNING.name().equals(run.status())) {
            jdbc.update("UPDATE runbook_run SET cancel_requested=1 WHERE id=?", runId);
            jdbc.update("UPDATE runbook_run_target SET status='CANCELLED',finished_at=? "
                    + "WHERE run_id=? AND status='PENDING'", Timestamp.from(Instant.now()), runId);
        } else {
            jdbc.update("UPDATE runbook_run SET status='CANCELLED',cancel_requested=1,finished_at=? WHERE id=?",
                    Timestamp.from(Instant.now()), runId);
            jdbc.update("UPDATE runbook_run_target SET status='CANCELLED',finished_at=? "
                    + "WHERE run_id=? AND status='PENDING'", Timestamp.from(Instant.now()), runId);
        }
        return detail(userId, runId);
    }

    /** 人工回滚：只对已产生副作用且未确认成功的作业开放。 */
    public RunView rollback(Long userId, long runId) {
        RunRow run = loadRun(userId, runId);
        if (!RunStatus.valueOf(run.status()).rollbackable()) {
            throw new BusinessException(409, "RUNBOOK_RUN_NOT_ROLLBACKABLE");
        }
        RunbookRow runbook = catalog.requireRunbook(userId, run.runbookId());
        VersionView version = catalog.loadVersion(run.runbookId(), run.version());
        Map<String, String> params = RunbookSupport.readStringMap(run.parametersJson());
        jdbc.update("UPDATE runbook_run SET status='ROLLING_BACK' WHERE id=?", runId);

        boolean allRolledBack = true;
        for (TargetRow target : loadTargets(runId)) {
            if (target.operationRunId() == null) {
                markRollback(runId, target.runtimeId(), TargetStatus.ROLLED_BACK, "未产生远端副作用，无需回滚");
                continue;
            }
            boolean ok = rollbackTarget(userId, run, version, params, target);
            allRolledBack = allRolledBack && ok;
        }
        jdbc.update("UPDATE runbook_run SET status=?,finished_at=? WHERE id=?",
                allRolledBack ? RunStatus.ROLLED_BACK.name() : RunStatus.ROLLBACK_FAILED.name(),
                Timestamp.from(Instant.now()), runId);
        return detail(userId, runId);
    }

    private boolean rollbackTarget(Long userId, RunRow run, VersionView version, Map<String, String> params,
                                   TargetRow target) {
        OperationRuntime runtime;
        try {
            runtime = registry.requireOwned(target.runtimeId(), userId);
        } catch (RuntimeException unavailable) {
            markRollback(run.id(), target.runtimeId(), TargetStatus.ROLLBACK_FAILED,
                    "运行连接不可用，回滚未执行：" + safeMessage(unavailable));
            return false;
        }
        ExecutionState state = new ExecutionState();
        String rollbackKey = "runbook:" + run.id() + ":" + target.runtimeId()
                + ":rollback:r" + Instant.now().getEpochSecond();
        OperationRunRecorder.RunHandle handle = runRecorder.start(new OperationRunRecorder.RunSpec(
                UUID.randomUUID().toString(), userId, runtime, "runbook-rollback:" + run.runbookId(),
                rollbackKey, Instant.now(), Instant.now().plusSeconds(300), MAX_OUTPUT_BYTES, LEASE_MS));
        runPhase(Phase.ROLLBACK, version.steps(), params, runtime, handle, Instant.now().plusSeconds(300),
                run.id(), state, new SequenceCounter(), false);
        runRecorder.finish(handle, state.failed ? "FAILED" : "SUCCEEDED", Instant.now());
        markRollback(run.id(), target.runtimeId(),
                state.failed ? TargetStatus.ROLLBACK_FAILED : TargetStatus.ROLLED_BACK,
                state.failed ? state.error : "回滚步骤已完成：" + state.output);
        return !state.failed;
    }

    /* ── 查询 ─────────────────────────────────────────────────────────── */

    @Transactional(readOnly = true)
    public List<RunView> listRuns(Long userId, String status, int limit) {
        int size = Math.max(1, Math.min(100, limit));
        String normalized = status == null || status.isBlank()
                ? null : status.trim().toUpperCase(java.util.Locale.ROOT);
        String tail = " WHERE r.user_id=?" + (normalized == null ? "" : " AND r.status=?")
                + " ORDER BY r.id DESC LIMIT ?";
        String base = """
                SELECT r.id,r.runbook_id,c.name AS runbook_name,r.version,r.user_id,r.environment,r.trigger_kind,
                       r.trigger_ref,r.status,r.risk_level,r.required_approvals,r.approval_count,r.cancel_requested,
                       r.content_hash,r.created_at,r.started_at,r.finished_at,r.note,r.total_targets,
                       r.succeeded_count,r.failed_count,r.unknown_count,r.cancelled_count,r.skipped_count
                  FROM runbook_run r JOIN runbook c ON c.id=r.runbook_id
                """;
        List<Map<String, Object>> rows = normalized == null
                ? jdbc.queryForList(base + tail, userId, size)
                : jdbc.queryForList(base + tail, userId, normalized, size);
        List<RunView> views = new ArrayList<>();
        for (Map<String, Object> row : rows) views.add(toRunView(row, List.of()));
        return views;
    }

    @Transactional(readOnly = true)
    public RunView detail(Long userId, long runId) {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT r.id,r.runbook_id,c.name AS runbook_name,r.version,r.user_id,r.environment,r.trigger_kind,
                       r.trigger_ref,r.status,r.risk_level,r.required_approvals,r.approval_count,r.cancel_requested,
                       r.content_hash,r.created_at,r.started_at,r.finished_at,r.note,r.total_targets,
                       r.succeeded_count,r.failed_count,r.unknown_count,r.cancelled_count,r.skipped_count
                  FROM runbook_run r JOIN runbook c ON c.id=r.runbook_id
                 WHERE r.id=? AND r.user_id=?
                """, runId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "RUNBOOK_RUN_NOT_FOUND");
        List<TargetView> targets = jdbc.query("""
                SELECT id,runtime_id,target_label,batch_no,canary,status,attempt,operation_run_id,exit_code,
                       output_excerpt,error,pre_check_status,post_check_status,rollback_status,rollback_output,
                       started_at,finished_at,dispatch_status,dispatched_at,executed_at,verified_at
                  FROM runbook_run_target WHERE run_id=?
                 ORDER BY batch_no,canary DESC,runtime_id,id
                """, (result, ignored) -> new TargetView(result.getLong("id"), result.getString("runtime_id"),
                result.getString("target_label"), result.getInt("batch_no"), result.getBoolean("canary"),
                result.getString("status"), result.getInt("attempt"),
                (Long) result.getObject("operation_run_id"), (Integer) result.getObject("exit_code"),
                result.getString("output_excerpt"), result.getString("error"), result.getString("pre_check_status"),
                result.getString("post_check_status"), result.getString("rollback_status"),
                result.getString("rollback_output"), instant(result.getTimestamp("started_at")),
                instant(result.getTimestamp("finished_at")), result.getString("dispatch_status"),
                instant(result.getTimestamp("dispatched_at")), instant(result.getTimestamp("executed_at")),
                instant(result.getTimestamp("verified_at"))), runId);
        Map<String, Object> row = rows.get(0);
        return new RunView(((Number) row.get("id")).longValue(), ((Number) row.get("runbook_id")).longValue(),
                (String) row.get("runbook_name"), ((Number) row.get("version")).intValue(),
                ((Number) row.get("user_id")).longValue(), (String) row.get("environment"),
                (String) row.get("trigger_kind"), (String) row.get("trigger_ref"), (String) row.get("status"),
                (String) row.get("risk_level"), ((Number) row.get("required_approvals")).intValue(),
                ((Number) row.get("approval_count")).intValue(), truthy(row.get("cancel_requested")),
                (String) row.get("content_hash"), instant((Timestamp) row.get("created_at")),
                instant((Timestamp) row.get("started_at")), instant((Timestamp) row.get("finished_at")),
                (String) row.get("note"), ((Number) row.get("total_targets")).intValue(),
                ((Number) row.get("succeeded_count")).intValue(), ((Number) row.get("failed_count")).intValue(),
                ((Number) row.get("unknown_count")).intValue(), ((Number) row.get("cancelled_count")).intValue(),
                ((Number) row.get("skipped_count")).intValue(), targets);
    }

    /* ── 定时执行 ─────────────────────────────────────────────────────── */

    @Transactional
    public ScheduleView createSchedule(Long userId, long runbookId, String cronExpr, String environment,
                                       Instant nextFireAt) {
        RunbookRow runbook = catalog.requireRunbook(userId, runbookId);
        if (!SentinelVariables.validCron(cronExpr)) {
            throw new BusinessException(400, "RUNBOOK_SCHEDULE_CRON_INVALID");
        }
        if (nextFireAt == null) throw new BusinessException(400, "RUNBOOK_SCHEDULE_NEXT_FIRE_REQUIRED");
        Environment env = Environment.of(environment == null ? runbook.environment() : environment);
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO runbook_schedule(runbook_id,user_id,cron_expr,environment,enabled,next_fire_at) "
                            + "VALUES(?,?,?,?,1,?)", Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, runbookId);
            statement.setLong(2, userId);
            statement.setString(3, cronExpr.trim());
            statement.setString(4, env.name());
            statement.setTimestamp(5, nextFireAt == null ? null : Timestamp.from(nextFireAt));
            return statement;
        }, keys);
        return scheduleView(generatedId(keys));
    }

    @Transactional(readOnly = true)
    public List<ScheduleView> listSchedules(Long userId) {
        List<Long> ids = jdbc.queryForList("SELECT id FROM runbook_schedule WHERE user_id=? ORDER BY id DESC LIMIT 100",
                Long.class, userId);
        List<ScheduleView> views = new ArrayList<>();
        for (Long id : ids) views.add(scheduleView(id));
        return views;
    }

    @Transactional
    public void deleteSchedule(Long userId, long id) {
        int deleted = jdbc.update("DELETE FROM runbook_schedule WHERE id=? AND user_id=?", id, userId);
        if (deleted == 0) throw new BusinessException(404, "RUNBOOK_SCHEDULE_NOT_FOUND");
    }

    /** 到点只生成"等待绑定目标"的作业，不会自动执行。 */
    @Transactional
    public int fireDueSchedules() {
        List<Long> due = jdbc.queryForList("""
                SELECT s.id FROM runbook_schedule s JOIN runbook r ON r.id=s.runbook_id
                 WHERE s.enabled=1 AND r.enabled=1 AND r.current_version IS NOT NULL
                   AND s.next_fire_at IS NOT NULL AND s.next_fire_at<=NOW()
                 ORDER BY s.id LIMIT 20
                """, Long.class);
        int fired = 0;
        for (Long id : due) {
            Map<String, Object> row = jdbc.queryForMap(
                    "SELECT runbook_id,user_id FROM runbook_schedule WHERE id=?", id);
            long runbookId = ((Number) row.get("runbook_id")).longValue();
            long userId = ((Number) row.get("user_id")).longValue();
            try {
                createTriggeredRun(userId, runbookId, Trigger.SCHEDULE, String.valueOf(id),
                        "schedule:" + id + ":" + Instant.now().getEpochSecond());
                fired++;
            } catch (RuntimeException skipped) {
                // 单条失败不影响其它调度；保留 last_fire_at 说明"尝试过"。
            }
            // 定时是"一次性装填"：触发后自动停用，避免重复扫描把同一时刻反复触发。
            jdbc.update("UPDATE runbook_schedule SET last_fire_at=NOW(),next_fire_at=NULL,enabled=0 WHERE id=?", id);
        }
        return fired;
    }

    /** 重新装填定时：显式给出下一次触发时间后才重新启用。 */
    @Transactional
    public ScheduleView rearmSchedule(Long userId, long id, Instant nextFireAt) {
        if (nextFireAt == null) throw new BusinessException(400, "RUNBOOK_SCHEDULE_NEXT_FIRE_REQUIRED");
        int updated = jdbc.update("UPDATE runbook_schedule SET next_fire_at=?,enabled=1 WHERE id=? AND user_id=?",
                Timestamp.from(nextFireAt), id, userId);
        if (updated == 0) throw new BusinessException(404, "RUNBOOK_SCHEDULE_NOT_FOUND");
        return scheduleView(id);
    }

    /* ── 事件触发 ─────────────────────────────────────────────────────── */

    @Transactional
    public TriggerView bindAlertTrigger(Long userId, long runbookId, String minSeverity) {
        catalog.requireRunbook(userId, runbookId);
        String severity = minSeverity == null ? "P1" : minSeverity.trim().toUpperCase(java.util.Locale.ROOT);
        if (RunbookSupport.severityRank(severity) > 3) throw new BusinessException(400, "RUNBOOK_TRIGGER_SEVERITY_INVALID");
        try {
            jdbc.update("INSERT INTO runbook_trigger(runbook_id,user_id,event_type,min_severity,enabled) "
                    + "VALUES(?,?,'ALERT',?,1)", runbookId, userId, severity);
        } catch (DuplicateKeyException exists) {
            throw new BusinessException(409, "RUNBOOK_TRIGGER_ALREADY_BOUND");
        }
        return triggerView(runbookId, userId);
    }

    @Transactional(readOnly = true)
    public List<TriggerView> listTriggers(Long userId) {
        return jdbc.query("""
                SELECT t.runbook_id,t.user_id,t.event_type,t.min_severity,t.enabled,c.name AS runbook_name
                  FROM runbook_trigger t JOIN runbook c ON c.id=t.runbook_id
                 WHERE t.user_id=? ORDER BY t.id DESC LIMIT 100
                """, (result, ignored) -> new TriggerView(result.getLong("runbook_id"),
                result.getString("runbook_name"), result.getString("event_type"),
                result.getString("min_severity"), result.getBoolean("enabled")), userId);
    }

    @Transactional
    public void deleteTrigger(Long userId, long runbookId, String eventType) {
        int deleted = jdbc.update("DELETE FROM runbook_trigger WHERE runbook_id=? AND user_id=? AND event_type=?",
                runbookId, userId, eventType == null ? "ALERT" : eventType.trim().toUpperCase(java.util.Locale.ROOT));
        if (deleted == 0) throw new BusinessException(404, "RUNBOOK_TRIGGER_NOT_FOUND");
    }

    /**
     * 告警 → 作业：同一告警对同一 Runbook 只生成一条待绑定作业（幂等键兜底）。
     */
    @Transactional
    public int fireAlertTriggers(int windowMinutes, int limit) {
        Instant since = Instant.now().minus(Duration.ofMinutes(Math.max(1, windowMinutes)));
        List<Map<String, Object>> triggers = jdbc.queryForList(
                "SELECT runbook_id,user_id,min_severity FROM runbook_trigger WHERE enabled=1 AND event_type='ALERT' LIMIT ?",
                Math.max(1, Math.min(100, limit)));
        int created = 0;
        for (Map<String, Object> trigger : triggers) {
            long runbookId = ((Number) trigger.get("runbook_id")).longValue();
            long userId = ((Number) trigger.get("user_id")).longValue();
            String minSeverity = (String) trigger.get("min_severity");
            List<Map<String, Object>> alerts = jdbc.queryForList("""
                    SELECT a.id,a.severity FROM sentinel_alert a
                      LEFT JOIN sentinel_task t ON t.id=a.task_id
                      LEFT JOIN sentinel_alert_rule r ON r.id=a.rule_id
                     WHERE (t.user_id=? OR r.user_id=?) AND a.fired_at>=? AND a.status<>'CLOSED'
                     ORDER BY a.id DESC LIMIT 50
                    """, userId, userId, Timestamp.from(since));
            for (Map<String, Object> alert : alerts) {
                String severity = (String) alert.get("severity");
                if (RunbookSupport.severityRank(severity) > RunbookSupport.severityRank(minSeverity)) continue;
                long alertId = ((Number) alert.get("id")).longValue();
                try {
                    long runId = createTriggeredRun(userId, runbookId, Trigger.ALERT, String.valueOf(alertId),
                            "alert:" + alertId + ":" + runbookId);
                    if (runId > 0) created++;
                } catch (RuntimeException skipped) {
                    // 单个绑定不可用（例如版本未发布、必填参数无默认值）不影响其它绑定。
                }
            }
        }
        return created;
    }

    /* ── 内部：写入与映射 ─────────────────────────────────────────────── */

    private long insertRunSkeleton(Long userId, RunbookRow runbook, VersionView version, Trigger trigger,
                                   String triggerRef, String idempotencyKey, RunStatus status) {
        // 骨架只预填默认值：必填但无默认值的参数在计划/绑定目标阶段再校验，
        // 否则"创建待绑定作业"会因为缺参数被误判为配置错误。
        Map<String, String> params = seedParameters(version.parameters());
        String hash = expectedContentHash(version, params, List.of());
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO runbook_run(runbook_id,version_id,version,user_id,environment,trigger_kind,trigger_ref,
                        idempotency_key,status,parameters_json,target_selector_json,target_snapshot_json,content_hash,
                        risk_level,required_approvals,approval_count,total_targets)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0)
                    """, Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, runbook.id());
            statement.setLong(2, version.id());
            statement.setInt(3, version.version());
            statement.setLong(4, userId);
            statement.setString(5, runbook.environment());
            statement.setString(6, trigger.name());
            statement.setString(7, triggerRef);
            statement.setString(8, idempotencyKey);
            statement.setString(9, status.name());
            statement.setString(10, RunbookSupport.toJson(params));
            statement.setString(11, RunbookSupport.toJson(selector(List.of())));
            statement.setString(12, RunbookSupport.toJson(List.of()));
            statement.setString(13, hash);
            statement.setString(14, version.riskLevel());
            return statement;
        }, keys);
        return generatedId(keys);
    }

    private void insertTarget(long runId, String runtimeId, int batchNo, boolean canary) {
        jdbc.update("""
                INSERT INTO runbook_run_target(run_id,runtime_id,target_label,batch_no,canary,status,attempt)
                VALUES(?,?,?,?,?, 'PENDING',0)
                """, runId, runtimeId, runtimeId, batchNo, canary);
    }

    private boolean markRunning(long runId, String runtimeId, int attempt, Instant startedAt) {
        // 只有仍待派发的目标才能进入 RUNNING：取消会把 PENDING 直接置为 CANCELLED，
        // 已排在线程池里但尚未开始的目标必须在这里被挡住，不能先派发再补记取消。
        int updated = jdbc.update("UPDATE runbook_run_target SET status='RUNNING',attempt=?,started_at=?,finished_at=NULL "
                + "WHERE run_id=? AND runtime_id=? AND status IN ('PENDING','TIMEOUT')",
                attempt, Timestamp.from(startedAt), runId, runtimeId);
        return updated > 0;
    }

    private void finishTarget(long runId, String runtimeId, TargetStatus status, int attempt, Long operationRunId,
                              Integer exitCode, String output, String error, String preCheckStatus,
                              String postCheckStatus, String rollbackStatus, String rollbackOutput, Instant startedAt,
                              String dispatchStatus, Instant dispatchedAt, Instant executedAt, Instant verifiedAt) {
        Instant finishedAt = Instant.now();
        jdbc.update("""
                UPDATE runbook_run_target SET status=?,attempt=?,operation_run_id=?,exit_code=?,output_excerpt=?,
                       error=?,pre_check_status=?,post_check_status=?,rollback_status=?,rollback_output=?,
                       started_at=?,finished_at=?,dispatch_status=?,dispatched_at=?,executed_at=?,verified_at=?
                 WHERE run_id=? AND runtime_id=?
                """, status.name(), attempt, operationRunId, exitCode, RunbookSupport.truncate(output, MAX_OUTPUT_CHARS),
                RunbookSupport.truncate(error, 500), preCheckStatus, postCheckStatus, rollbackStatus,
                RunbookSupport.truncate(rollbackOutput, MAX_OUTPUT_CHARS), Timestamp.from(startedAt),
                Timestamp.from(finishedAt), dispatchStatus,
                dispatchedAt == null ? null : Timestamp.from(dispatchedAt),
                executedAt == null ? null : Timestamp.from(executedAt),
                verifiedAt == null ? null : Timestamp.from(verifiedAt), runId, runtimeId);
    }

    private void markSkipped(long runId, String runtimeId, String reason) {
        jdbc.update("UPDATE runbook_run_target SET status='SKIPPED',error=?,finished_at=? "
                + "WHERE run_id=? AND runtime_id=?", RunbookSupport.truncate(reason, 500),
                Timestamp.from(Instant.now()), runId, runtimeId);
    }

    private void markRollback(long runId, String runtimeId, TargetStatus status, String detail) {
        jdbc.update("UPDATE runbook_run_target SET status=?,rollback_status=?,rollback_output=?,finished_at=? "
                + "WHERE run_id=? AND runtime_id=?", status.name(), status.name(),
                RunbookSupport.truncate(detail, MAX_OUTPUT_CHARS),
                Timestamp.from(Instant.now()), runId, runtimeId);
    }

    private void finishRun(long runId) {
        // 汇总以库内目标状态为准：取消时后续批次由 SQL 直接置为 CANCELLED，
        // 它们不会出现在本轮 outcomes 里，只用内存结果会漏计。
        int succeeded = targetCount(runId, "SUCCEEDED");
        int failed = targetCount(runId, "FAILED") + targetCount(runId, "ROLLED_BACK")
                + targetCount(runId, "ROLLBACK_FAILED");
        int unknown = targetCount(runId, "UNKNOWN");
        int cancelled = targetCount(runId, "CANCELLED");
        int skipped = targetCount(runId, "SKIPPED");
        int total = targetCount(runId);

        RunStatus status;
        if (unknown > 0) {
            status = RunStatus.UNKNOWN;
        } else if (cancelled > 0 && succeeded == 0 && failed == 0) {
            status = RunStatus.CANCELLED;
        } else if (succeeded == total && total > 0) {
            status = RunStatus.SUCCEEDED;
        } else if (succeeded > 0) {
            status = RunStatus.PARTIAL;
        } else {
            status = RunStatus.FAILED;
        }
        String note = "成功 " + succeeded + "，失败 " + failed + "，未知 " + unknown
                + "，取消 " + cancelled + "，跳过 " + skipped;
        jdbc.update("""
                UPDATE runbook_run SET status=?,finished_at=?,succeeded_count=?,failed_count=?,unknown_count=?,
                       cancelled_count=?,skipped_count=?,note=?
                 WHERE id=?
                """, status.name(), Timestamp.from(Instant.now()), succeeded, failed, unknown, cancelled, skipped,
                note, runId);
    }

    private int targetCount(long runId, String status) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM runbook_run_target WHERE run_id=? AND status=?",
                Integer.class, runId, status);
        return count == null ? 0 : count;
    }

    private int targetCount(long runId) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM runbook_run_target WHERE run_id=?",
                Integer.class, runId);
        return count == null ? 0 : count;
    }

    /* ── 内部：读取与校验 ─────────────────────────────────────────────── */

    private RunRow loadRun(Long userId, long runId) {
        if (userId == null) throw new BusinessException(401, "RUNBOOK_USER_REQUIRED");
        return loadRunWhere("id=? AND user_id=?", runId, userId);
    }

    private RunRow loadRunById(long runId) {
        return loadRunWhere("id=?", runId);
    }

    private RunRow loadRunWhere(String where, Object... args) {
        List<RunRow> rows = jdbc.query("""
                SELECT id,runbook_id,version_id,version,user_id,environment,trigger_kind,trigger_ref,status,
                       parameters_json,target_snapshot_json,content_hash,risk_level,required_approvals,approval_count,
                       approved_by,second_approver_id,cancel_requested,created_at,started_at,finished_at,nonce_hash
                  FROM runbook_run WHERE """ + " " + where, (result, ignored) -> new RunRow(
                result.getLong("id"), result.getLong("runbook_id"),
                result.getLong("version_id"), result.getInt("version"), result.getLong("user_id"),
                result.getString("environment"), result.getString("trigger_kind"), result.getString("trigger_ref"),
                result.getString("status"), result.getString("parameters_json"),
                result.getString("target_snapshot_json"), result.getString("content_hash"),
                result.getString("risk_level"), result.getInt("required_approvals"),
                result.getInt("approval_count"), (Long) result.getObject("approved_by"),
                (Long) result.getObject("second_approver_id"), result.getBoolean("cancel_requested"),
                instant(result.getTimestamp("created_at")), instant(result.getTimestamp("started_at")),
                instant(result.getTimestamp("finished_at")), result.getString("nonce_hash")), args);
        if (rows.isEmpty()) throw new BusinessException(404, "RUNBOOK_RUN_NOT_FOUND");
        return rows.get(0);
    }

    private List<TargetRow> loadTargets(long runId) {
        return jdbc.query("""
                SELECT id,run_id,runtime_id,target_label,batch_no,canary,status,attempt,operation_run_id
                  FROM runbook_run_target WHERE run_id=? ORDER BY batch_no,canary DESC,runtime_id,id
                """, (result, ignored) -> new TargetRow(result.getLong("id"), result.getLong("run_id"),
                result.getString("runtime_id"), result.getString("target_label"), result.getInt("batch_no"),
                result.getBoolean("canary"), result.getString("status"), result.getInt("attempt"),
                (Long) result.getObject("operation_run_id")), runId);
    }

    private boolean cancelRequestedNow(long runId) {
        Boolean requested = jdbc.queryForObject("SELECT cancel_requested FROM runbook_run WHERE id=?",
                Boolean.class, runId);
        return Boolean.TRUE.equals(requested);
    }

    private List<String> normalizeTargets(Long userId, List<String> runtimeIds) {
        if (runtimeIds == null || runtimeIds.isEmpty()) {
            throw new BusinessException(400, "RUNBOOK_TARGETS_REQUIRED");
        }
        List<String> targets = runtimeIds.stream().filter(RunbookSupport::hasText)
                .map(String::trim).distinct().toList();
        if (targets.isEmpty()) throw new BusinessException(400, "RUNBOOK_TARGETS_REQUIRED");
        for (String runtimeId : targets) registry.requireOwned(runtimeId, userId);
        return targets;
    }

    private Map<String, String> resolveParameters(List<ParameterSpec> schema, Map<String, String> raw) {
        Map<String, String> supplied = raw == null ? Map.of() : raw;
        Map<String, String> resolved = new LinkedHashMap<>();
        List<String> known = new ArrayList<>();
        for (ParameterSpec spec : schema) {
            known.add(spec.name());
            String value = supplied.get(spec.name());
            if (value == null || value.isBlank()) {
                if (spec.required() && (spec.defaultValue() == null || spec.defaultValue().isBlank())) {
                    throw new BusinessException(400, "RUNBOOK_PARAMETER_MISSING:" + spec.name());
                }
                value = spec.defaultValue();
            }
            if (value == null) continue;
            PatternHolder holder = new PatternHolder(spec.pattern());
            RunbookCatalogService.assertType(spec.name(), spec.type(), value, holder.pattern);
            resolved.put(spec.name(), value);
        }
        for (String name : supplied.keySet()) {
            if (!known.contains(name)) throw new BusinessException(400, "RUNBOOK_PARAMETER_UNKNOWN:" + name);
        }
        return resolved;
    }

    private Map<String, String> seedParameters(List<ParameterSpec> schema) {
        Map<String, String> seed = new LinkedHashMap<>();
        for (ParameterSpec spec : schema) {
            if (spec.defaultValue() != null) seed.put(spec.name(), spec.defaultValue());
        }
        return seed;
    }

    private List<StepPreview> renderSteps(List<StepView> steps, Map<String, String> params) {
        List<StepPreview> previews = new ArrayList<>();
        for (StepView step : steps) {
            try {
                SentinelVariables.Result substituted = SentinelVariables.applyChecked(step.body(), params);
                if (!substituted.unresolved().isEmpty()) {
                    throw new BusinessException(400, "RUNBOOK_PARAMETER_UNRESOLVED:"
                            + String.join("、", substituted.unresolved()));
                }
                previews.add(new StepPreview(step.phase(), step.seq(), step.name(), substituted.body()));
            } catch (IllegalArgumentException unsafe) {
                throw new BusinessException(400, unsafe.getMessage());
            }
        }
        return previews;
    }

    private String expectedContentHash(VersionView version, Map<String, String> params, List<String> targets) {
        List<String> canonicalSteps = version.steps().stream()
                .map(step -> step.phase() + ":" + step.seq() + ":" + step.name() + ":" + step.body()
                        + ":" + step.expectExitCode() + ":" + step.onFailure())
                .toList();
        return RunbookSupport.contentHash(version.id(), version.version(), params, targets, canonicalSteps);
    }

    private Map<String, Object> selector(List<String> targets) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("runtimeIds", targets);
        map.put("resolution", "会话级运行连接：计划时显式指定，并按批准时快照执行");
        return map;
    }

    private static String phaseStatus(ExecutionState state) {
        if (state.cancelled) return "CANCELLED";
        if (state.uncertain) return "UNKNOWN";
        if (state.timedOut) return "TIMEOUT";
        if (state.failed && Phase.PRE_CHECK.name().equals(state.failedPhase)) return "FAILED";
        return "SUCCEEDED";
    }

    private static String bound(String value) {
        if (value == null) return "";
        return value.length() <= MAX_OUTPUT_CHARS ? value : value.substring(0, MAX_OUTPUT_CHARS);
    }

    private static boolean truncated(String stdout, String stderr) {
        return (stdout != null && stdout.length() > MAX_OUTPUT_CHARS)
                || (stderr != null && stderr.length() > MAX_OUTPUT_CHARS);
    }

    private static String safeMessage(Throwable failure) {
        if (failure == null) return "UNKNOWN_ERROR";
        String message = failure.getMessage();
        return message == null || message.isBlank() ? failure.getClass().getSimpleName() : message;
    }

    private ScheduleView scheduleView(long id) {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT s.id,s.runbook_id,c.name AS runbook_name,s.cron_expr,s.environment,s.enabled,
                       s.last_fire_at,s.next_fire_at
                  FROM runbook_schedule s JOIN runbook c ON c.id=s.runbook_id WHERE s.id=?
                """, id);
        if (rows.isEmpty()) throw new BusinessException(404, "RUNBOOK_SCHEDULE_NOT_FOUND");
        Map<String, Object> row = rows.get(0);
        return new ScheduleView(((Number) row.get("id")).longValue(), ((Number) row.get("runbook_id")).longValue(),
                (String) row.get("runbook_name"), (String) row.get("cron_expr"), (String) row.get("environment"),
                truthy(row.get("enabled")), instant((Timestamp) row.get("last_fire_at")),
                instant((Timestamp) row.get("next_fire_at")));
    }

    private TriggerView triggerView(long runbookId, long userId) {
        Map<String, Object> row = jdbc.queryForMap("""
                SELECT t.runbook_id,t.user_id,t.event_type,t.min_severity,t.enabled,c.name AS runbook_name
                  FROM runbook_trigger t JOIN runbook c ON c.id=t.runbook_id
                 WHERE t.runbook_id=? AND t.user_id=?
                """, runbookId, userId);
        return new TriggerView(((Number) row.get("runbook_id")).longValue(), (String) row.get("runbook_name"),
                (String) row.get("event_type"), (String) row.get("min_severity"), truthy(row.get("enabled")));
    }

    private static Instant instant(Timestamp value) { return value == null ? null : value.toInstant(); }

    /** H2/MySQL 的 TINYINT(1) 经 queryForList 可能返回数字，统一按"非零即真"处理。 */
    private static boolean truthy(Object value) {
        if (value instanceof Boolean flag) return flag;
        if (value instanceof Number number) return number.intValue() != 0;
        return value != null && Boolean.parseBoolean(value.toString());
    }

    private static long generatedId(KeyHolder keys) {
        var keyList = keys.getKeyList();
        if (keyList.isEmpty()) throw new BusinessException(500, "RUNBOOK_WRITE_NO_ID");
        Object id = keyList.get(0).get("id");
        if (id == null) {
            Object only = keyList.get(0).values().stream().findFirst().orElse(null);
            if (only == null) throw new BusinessException(500, "RUNBOOK_WRITE_NO_ID");
            return ((Number) only).longValue();
        }
        return ((Number) id).longValue();
    }

    /* ── 视图与内部结构 ───────────────────────────────────────────────── */

    public record PlanResult(long runId, String status, String riskLevel, int requiredApprovals,
                             String confirmationNonce, String contentHash, List<String> targets,
                             List<StepPreview> steps, String nextStep, String note) {}

    public record StepPreview(String phase, int seq, String name, String command) {}

    public record TargetView(long id, String runtimeId, String targetLabel, int batchNo, boolean canary,
                             String status, int attempt, Long operationRunId, Integer exitCode, String outputExcerpt,
                             String error, String preCheckStatus, String postCheckStatus, String rollbackStatus,
                             String rollbackOutput, Instant startedAt, Instant finishedAt,
                             String dispatchStatus, Instant dispatchedAt, Instant executedAt, Instant verifiedAt) {}

    public record RunView(long id, long runbookId, String runbookName, int version, long userId, String environment,
                          String trigger, String triggerRef, String status, String riskLevel, int requiredApprovals,
                          int approvalCount, boolean cancelRequested, String contentHash, Instant createdAt,
                          Instant startedAt, Instant finishedAt, String note, int totalTargets, int succeeded,
                          int failed, int unknown, int cancelled, int skipped, List<TargetView> targets) {}

    public record ScheduleView(long id, long runbookId, String runbookName, String cronExpr, String environment,
                               boolean enabled, Instant lastFireAt, Instant nextFireAt) {}

    public record TriggerView(long runbookId, String runbookName, String eventType, String minSeverity, boolean enabled) {}

    record RunRow(long id, long runbookId, long versionId, int version, long userId, String environment,
                  String triggerKind, String triggerRef, String status, String parametersJson,
                  String targetSnapshotJson, String contentHash, String riskLevel, int requiredApprovals,
                  int approvalCount, Long approvedBy, Long secondApproverId, boolean cancelRequested,
                  Instant createdAt, Instant startedAt, Instant finishedAt, String nonceHash) {}

    record TargetRow(long id, long runId, String runtimeId, String targetLabel, int batchNo, boolean canary,
                     String status, int attempt, Long operationRunId) {}

    record TargetOutcome(String runtimeId, TargetStatus status, String error, Long operationRunId, Integer exitCode,
                         String output, String preCheckStatus, String failedPhase, int attempt) {}

    /** 单目标执行的累积状态；阶段之间只传这一份，避免状态散落在局部变量里。 */
    private static final class SequenceCounter {
        int value;
    }

    private static final class ExecutionState {
        boolean dispatched;
        Instant dispatchedAt;
        boolean cancelled;
        boolean timedOut;
        boolean uncertain;
        boolean failed;
        boolean continuedFailure;
        String failedPhase;
        String onFailure;
        String error;
        int lastExitCode = -1;
        String output = "";
    }

    /** 编译参数正则的轻量封装：保存阶段已校验可编译，这里只是复用同一口径。 */
    private static final class PatternHolder {
        private final java.util.regex.Pattern pattern;
        PatternHolder(String regex) {
            this.pattern = regex == null || regex.isBlank() ? null : java.util.regex.Pattern.compile(regex);
        }
    }

    private static RunView toRunView(Map<String, Object> row, List<TargetView> targets) {
        return new RunView(((Number) row.get("id")).longValue(), ((Number) row.get("runbook_id")).longValue(),
                (String) row.get("runbook_name"), ((Number) row.get("version")).intValue(),
                ((Number) row.get("user_id")).longValue(), (String) row.get("environment"),
                (String) row.get("trigger_kind"), (String) row.get("trigger_ref"), (String) row.get("status"),
                (String) row.get("risk_level"), ((Number) row.get("required_approvals")).intValue(),
                ((Number) row.get("approval_count")).intValue(), truthy(row.get("cancel_requested")),
                (String) row.get("content_hash"), instant((Timestamp) row.get("created_at")),
                instant((Timestamp) row.get("started_at")), instant((Timestamp) row.get("finished_at")),
                (String) row.get("note"), ((Number) row.get("total_targets")).intValue(),
                ((Number) row.get("succeeded_count")).intValue(), ((Number) row.get("failed_count")).intValue(),
                ((Number) row.get("unknown_count")).intValue(), ((Number) row.get("cancelled_count")).intValue(),
                ((Number) row.get("skipped_count")).intValue(), targets);
    }
}
