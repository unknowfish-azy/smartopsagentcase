package com.smartops.iac;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Objects;

/**
 * OPS-12：IaC / GitOps 的计划、审批、下发、变更后验证、发布历史与漂移分析。
 *
 * <p>治理顺序固定：分析 → 保存计划 → 显式审批（销毁型计划需单独确认）→ 下发（SENT）
 * → 引用真实运行记录确认执行结果 → 独立验证 → 写入发布历史。任何一步都不冒充下一步：
 * {@code SENT} 不等于执行成功，执行成功也不等于验证通过。</p>
 *
 * <p>复用既有 Run / 审批 / 审计体系：apply 必须引用 operation_run_record 的 trace_id，
 * 不另建执行链；状态锁与并发变更按 workspace 判定。</p>
 */
@Service
public class IacService {

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final ObjectMapper JSON = new ObjectMapper();

    private final JdbcTemplate jdbc;

    public IacService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /* ── 计划 ─────────────────────────────────────────────────────────── */

    public TerraformPlanAnalyzer.Analysis analyze(String planJson) {
        return TerraformPlanAnalyzer.analyze(planJson);
    }

    public PlanView plan(long userId, PlanRequest request) {
        if (request == null || !hasText(request.workspace())) {
            throw new BusinessException(400, "IAC_WORKSPACE_REQUIRED: 缺少 workspace");
        }
        if (!hasText(request.environment())) {
            throw new BusinessException(400, "IAC_ENVIRONMENT_REQUIRED: 缺少 environment");
        }
        TerraformPlanAnalyzer.Analysis analysis = analyze(request.planJson());
        String workspace = request.workspace().trim();
        String environment = request.environment().trim();

        Long rollbackOf = request.rollbackOfReleaseId();
        if (rollbackOf != null) {
            ReleaseRow target = requireRelease(userId, rollbackOf);
            if (!workspace.equals(target.workspace())) {
                throw new BusinessException(409, "IAC_ROLLBACK_WORKSPACE_MISMATCH: 回滚目标不在同一 workspace");
            }
            if (!Objects.equals(trimToNull(request.commitSha()), target.commitSha())
                    || !Objects.equals(trimToNull(request.imageDigest()), target.imageDigest())) {
                throw new BusinessException(409,
                        "IAC_ROLLBACK_TARGET_MISMATCH: 计划的 commit/镜像 digest 与回滚目标发布不一致");
            }
        }

        Long existing = jdbc.query("""
                SELECT id FROM iac_plan_record
                 WHERE user_id=? AND workspace=? AND plan_digest=?
                """, rs -> rs.next() ? rs.getLong(1) : null, userId, workspace, analysis.digest());
        if (existing != null) {
            // 同一份计划重复提交返回同一条记录，避免产生多个"已批准"副本。
            return detail(userId, existing);
        }

        jdbc.update("""
                INSERT INTO iac_plan_record
                    (user_id,workspace,environment,plan_digest,plan_summary_json,create_count,update_count,
                     delete_count,replace_count,change_count,truncated,destroy_detected,terraform_version,
                     state_serial,state_lineage,commit_sha,image_digest,release_version,rollback_of_release_id,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, userId, workspace, environment, analysis.digest(),
                TerraformPlanAnalyzer.summaryJson(analysis),
                analysis.createCount(), analysis.updateCount(), analysis.deleteCount(), analysis.replaceCount(),
                analysis.changeCount(), bool(analysis.truncated()), bool(analysis.destroyDetected()),
                analysis.terraformVersion(), analysis.stateSerial(), analysis.stateLineage(),
                trimToNull(request.commitSha()), trimToNull(request.imageDigest()),
                trimToNull(request.releaseVersion()), rollbackOf, "PLANNED");
        long id = jdbc.queryForObject("""
                SELECT id FROM iac_plan_record WHERE user_id=? AND workspace=? AND plan_digest=?
                """, Long.class, userId, workspace, analysis.digest());
        return detail(userId, id);
    }

    public PlanView detail(long userId, long planId) {
        return planRow(requirePlan(userId, planId));
    }

    /**
     * 审批计划：销毁型计划必须显式确认，审批结果绑定计划摘要与批准人。
     */
    public PlanView approve(long userId, long planId, boolean confirmDestroy) {
        PlanRow plan = requirePlan(userId, planId);
        if (!"PLANNED".equals(plan.status())) {
            throw new BusinessException(409, "IAC_PLAN_NOT_PENDING_APPROVAL: 当前状态 " + plan.status());
        }
        if (plan.destroyDetected() && !confirmDestroy) {
            throw new BusinessException(409,
                    "IAC_DESTROY_NOT_CONFIRMED: 计划包含 delete/replace（" + plan.deleteCount()
                            + " 删除 / " + plan.replaceCount() + " 替换），需显式确认销毁");
        }
        String nonce = nonce();
        jdbc.update("""
                UPDATE iac_plan_record
                   SET status='APPROVED',approval_nonce=?,approved_by=?,approved_at=?
                 WHERE id=? AND status='PLANNED'
                """, nonce, userId, Timestamp.from(Instant.now()), planId);
        return detail(userId, planId);
    }

    /* ── 下发 / 执行证据 / 验证 ───────────────────────────────────────── */

    /**
     * 下发计划：校验审批码、workspace 状态锁与计划新鲜度，记录 SENT。
     *
     * <p>下发只代表命令已发出；真正的执行结果必须由 {@link #completeApply} 引用运行记录确认。</p>
     */
    @Transactional
    public ApplyView dispatch(long userId, long planId, String confirmationNonce) {
        PlanRow plan = requirePlan(userId, planId);
        if (!"APPROVED".equals(plan.status())) {
            throw new BusinessException(409, "IAC_PLAN_NOT_APPROVED: 当前状态 " + plan.status());
        }
        if (!Objects.equals(trimToNull(confirmationNonce), plan.approvalNonce())) {
            throw new BusinessException(409, "IAC_APPROVAL_NONCE_MISMATCH: 审批码不匹配");
        }
        int locked = jdbc.queryForObject("""
                SELECT COUNT(*) FROM iac_apply_record
                 WHERE user_id=? AND workspace=? AND status='DISPATCHED'
                """, Integer.class, userId, plan.workspace());
        if (locked > 0) {
            throw new BusinessException(409, "IAC_STATE_LOCKED: 该 workspace 有变更正在执行");
        }
        Long newerPlan = jdbc.query("""
                SELECT id FROM iac_plan_record
                 WHERE user_id=? AND workspace=? AND id>? AND plan_digest<>?
                 ORDER BY id DESC LIMIT 1
                """, rs -> rs.next() ? rs.getLong(1) : null, userId, plan.workspace(), planId, plan.planDigest());
        if (newerPlan != null) {
            // 计划之后又出现了不同内容的计划：状态可能已变化，旧计划不得继续下发。
            throw new BusinessException(409, "IAC_PLAN_STALE: 已存在更新的计划 " + newerPlan + "，请重新审批");
        }

        Instant now = Instant.now();
        // SEC-09：直接取本次插入主键，避免同 plan 并发下发时 MAX(id) 取到别人的 apply 记录。
        var keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("""
                    INSERT INTO iac_apply_record
                        (plan_id,user_id,workspace,status,dispatch_status,dispatched_at,verification_status)
                    VALUES (?,?,?,?,?,?,?)
                    """, new String[]{"id"});
            statement.setObject(1, planId);
            statement.setObject(2, userId);
            statement.setObject(3, plan.workspace());
            statement.setObject(4, "DISPATCHED");
            statement.setObject(5, "SENT");
            statement.setObject(6, Timestamp.from(now));
            statement.setObject(7, "UNVERIFIED");
            return statement;
        }, keys);
        jdbc.update("UPDATE iac_plan_record SET status='APPLYING' WHERE id=?", planId);
        long applyId = keys.getKey().longValue();
        return applyRow(requireApply(userId, applyId));
    }

    /**
     * 用真实运行记录确认执行结果：只有 Run 状态为 SUCCEEDED 且退出码为 0 才记 APPLIED。
     */
    public ApplyView completeApply(long userId, long applyId, String runTraceId, Integer exitCode) {
        ApplyRow apply = requireApply(userId, applyId);
        if (!"DISPATCHED".equals(apply.status())) {
            throw new BusinessException(409, "IAC_APPLY_NOT_DISPATCHED: 当前状态 " + apply.status());
        }
        if (!hasText(runTraceId)) {
            throw new BusinessException(400, "IAC_RUN_EVIDENCE_REQUIRED: 缺少运行记录 trace_id");
        }
        String runStatus = jdbc.query("""
                SELECT status FROM operation_run_record WHERE trace_id=? AND user_id=?
                """, rs -> rs.next() ? rs.getString(1) : null, runTraceId.trim(), userId);
        if (runStatus == null) {
            throw new BusinessException(400, "IAC_RUN_EVIDENCE_INVALID: 找不到对应的运行记录");
        }
        String status;
        String detail;
        Instant appliedAt = null;
        if ("SUCCEEDED".equals(runStatus) && exitCode != null && exitCode == 0) {
            status = "APPLIED";
            appliedAt = Instant.now();
            detail = "运行记录成功，退出码 0";
        } else if ("UNCERTAIN".equals(runStatus)) {
            status = "UNCERTAIN";
            detail = "远端动作结果不确定，不冒充成功";
        } else if ("SUCCEEDED".equals(runStatus)) {
            status = "FAILED";
            detail = "运行记录显示成功但退出码为 " + exitCode + "，证据矛盾";
        } else {
            status = "FAILED";
            detail = "运行记录状态 " + runStatus + "，未确认变更成功";
        }
        Instant finishedAt = Instant.now();
        jdbc.update("""
                UPDATE iac_apply_record
                   SET status=?,run_trace_id=?,exit_code=?,applied_at=?,verification_detail=?
                 WHERE id=?
                """, status, runTraceId.trim(), exitCode,
                appliedAt == null ? null : Timestamp.from(appliedAt), detail, applyId);
        jdbc.update("UPDATE iac_plan_record SET status=? WHERE id=?", status, apply.planId());
        if ("APPLIED".equals(status)) {
            recordRelease(userId, apply, appliedAt);
        }
        return applyRow(requireApply(userId, applyId));
    }

    /**
     * 变更后验证：至少一条检查，全部通过才记 VERIFIED；否则如实记 VERIFICATION_FAILED。
     */
    @Transactional
    public ApplyView verify(long userId, long applyId, List<Check> checks) {
        ApplyRow apply = requireApply(userId, applyId);
        if (!"APPLIED".equals(apply.status())) {
            throw new BusinessException(409, "IAC_APPLY_NOT_APPLIED: 当前状态 " + apply.status());
        }
        if (checks == null || checks.isEmpty()) {
            throw new BusinessException(400, "IAC_VERIFICATION_EVIDENCE_REQUIRED: 至少提供一条检查结果");
        }
        boolean passed = checks.stream().allMatch(check -> check != null && check.passed());
        String status = passed ? "VERIFIED" : "VERIFICATION_FAILED";
        String detail = checks.stream()
                .map(check -> (check == null ? "?" : check.name()) + "=" + (check == null ? "?" : check.passed()))
                .reduce((left, right) -> left + "; " + right).orElse("");
        Instant verifiedAt = passed ? Instant.now() : null;
        jdbc.update("""
                UPDATE iac_apply_record SET verification_status=?,verified_at=?,verification_detail=? WHERE id=?
                """, status, verifiedAt == null ? null : Timestamp.from(verifiedAt), detail, applyId);
        jdbc.update("""
                UPDATE iac_release_record SET status=?,verified_at=? WHERE apply_id=?
                """, status, verifiedAt == null ? null : Timestamp.from(verifiedAt), applyId);
        return applyRow(requireApply(userId, applyId));
    }

    /* ── 发布历史 / 漂移 ─────────────────────────────────────────────── */

    public List<ReleaseView> releases(long userId, String workspace) {
        List<ReleaseRow> rows = jdbc.query("""
                SELECT * FROM iac_release_record WHERE user_id=? AND workspace=? ORDER BY id DESC LIMIT 50
                """, RELEASE_MAPPER, userId, requireWorkspace(workspace));
        return rows.stream().map(this::releaseView).toList();
    }

    /**
     * 期望（最新计划）与实际（最后一次发布）差异；不把"计划已批准但未执行"算作已同步。
     */
    public DriftView drift(long userId, String workspace) {
        String scopedWorkspace = requireWorkspace(workspace);
        PlanRow plan = jdbc.query("""
                SELECT * FROM iac_plan_record WHERE user_id=? AND workspace=? ORDER BY id DESC LIMIT 1
                """, rs -> rs.next() ? PLAN_MAPPER.mapRow(rs, 0) : null, userId, scopedWorkspace);
        ReleaseRow release = jdbc.query("""
                SELECT * FROM iac_release_record WHERE user_id=? AND workspace=? ORDER BY id DESC LIMIT 1
                """, rs -> rs.next() ? RELEASE_MAPPER.mapRow(rs, 0) : null, userId, scopedWorkspace);
        if (plan == null && release == null) {
            return new DriftView(scopedWorkspace, "NO_HISTORY", false, "尚无计划与发布记录",
                    null, null, null, null, null, null);
        }
        if (release == null) {
            return new DriftView(scopedWorkspace, "NO_RELEASE", true, "有计划但从未成功发布",
                    plan.commitSha(), plan.imageDigest(), null, null, plan.id(), null);
        }
        if (plan == null) {
            return new DriftView(scopedWorkspace, "NO_PLAN", false, "只有发布历史，没有可比较的计划",
                    null, null, release.commitSha(), release.imageDigest(), null, release.id());
        }
        boolean sameCommit = Objects.equals(plan.commitSha(), release.commitSha());
        boolean sameImage = Objects.equals(plan.imageDigest(), release.imageDigest());
        boolean samePlan = plan.id() == release.planId();
        boolean drifted = !samePlan || !sameCommit || !sameImage;
        String reason = !drifted ? "期望与实际一致"
                : (!samePlan && sameCommit && sameImage)
                ? "最新计划尚未发布（plan " + plan.id() + " / release plan " + release.planId() + "）"
                : "commit 或镜像 digest 与最后发布不一致";
        return new DriftView(scopedWorkspace, drifted ? "DRIFT" : "IN_SYNC", drifted, reason,
                plan.commitSha(), plan.imageDigest(), release.commitSha(), release.imageDigest(),
                plan.id(), release.id());
    }

    /* ── 内部 ─────────────────────────────────────────────────────────── */

    private void recordRelease(long userId, ApplyRow apply, Instant appliedAt) {
        PlanRow plan = jdbc.queryForObject("SELECT * FROM iac_plan_record WHERE id=?", PLAN_MAPPER, apply.planId());
        Long previous = jdbc.query("""
                SELECT id FROM iac_release_record WHERE user_id=? AND workspace=? ORDER BY id DESC LIMIT 1
                """, rs -> rs.next() ? rs.getLong(1) : null, userId, apply.workspace());
        String direction = plan.rollbackOfReleaseId() == null ? "DEPLOY" : "ROLLBACK";
        String version = plan.releaseVersion() == null ? "plan-" + plan.id() : plan.releaseVersion();
        jdbc.update("""
                INSERT INTO iac_release_record
                    (user_id,workspace,environment,release_version,commit_sha,image_digest,plan_id,apply_id,
                     direction,status,applied_at,previous_release_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, userId, apply.workspace(), plan.environment(), version, plan.commitSha(), plan.imageDigest(),
                plan.id(), apply.id(), direction, "APPLIED", Timestamp.from(appliedAt), previous);
    }

    private PlanRow requirePlan(long userId, long planId) {
        PlanRow plan = jdbc.query("SELECT * FROM iac_plan_record WHERE id=?", rs ->
                rs.next() ? PLAN_MAPPER.mapRow(rs, 0) : null, planId);
        if (plan == null || plan.userId() != userId) {
            throw new BusinessException(404, "IAC_PLAN_NOT_FOUND: 计划不存在");
        }
        return plan;
    }

    private ApplyRow requireApply(long userId, long applyId) {
        ApplyRow apply = jdbc.query("SELECT * FROM iac_apply_record WHERE id=?", rs ->
                rs.next() ? APPLY_MAPPER.mapRow(rs, 0) : null, applyId);
        if (apply == null || apply.userId() != userId) {
            throw new BusinessException(404, "IAC_APPLY_NOT_FOUND: 下发记录不存在");
        }
        return apply;
    }

    private ReleaseRow requireRelease(long userId, long releaseId) {
        ReleaseRow release = jdbc.query("SELECT * FROM iac_release_record WHERE id=?", rs ->
                rs.next() ? RELEASE_MAPPER.mapRow(rs, 0) : null, releaseId);
        if (release == null || release.userId() != userId) {
            throw new BusinessException(404, "IAC_RELEASE_NOT_FOUND: 发布记录不存在");
        }
        return release;
    }

    private PlanView planRow(PlanRow plan) {
        return new PlanView(plan.id(), plan.workspace(), plan.environment(), plan.planDigest(),
                plan.createCount(), plan.updateCount(), plan.deleteCount(), plan.replaceCount(),
                plan.changeCount(), plan.destroyDetected(), plan.truncated(), plan.terraformVersion(),
                plan.stateSerial(), plan.commitSha(), plan.imageDigest(), plan.releaseVersion(),
                plan.rollbackOfReleaseId(), plan.status(), plan.approvalNonce(), plan.approvedBy(),
                plan.approvedAt(), plan.createdAt(), plan.changes());
    }

    private ApplyView applyRow(ApplyRow apply) {
        return new ApplyView(apply.id(), apply.planId(), apply.workspace(), apply.status(),
                apply.dispatchStatus(), apply.dispatchedAt(), apply.runTraceId(), apply.exitCode(),
                apply.appliedAt(), apply.verificationStatus(), apply.verifiedAt(), apply.verificationDetail());
    }

    private ReleaseView releaseView(ReleaseRow release) {
        return new ReleaseView(release.id(), release.workspace(), release.environment(),
                release.releaseVersion(), release.commitSha(), release.imageDigest(), release.planId(),
                release.applyId(), release.direction(), release.status(), release.appliedAt(),
                release.verifiedAt(), release.previousReleaseId());
    }

    private static String requireWorkspace(String workspace) {
        if (!hasText(workspace)) throw new BusinessException(400, "IAC_WORKSPACE_REQUIRED: 缺少 workspace");
        return workspace.trim();
    }

    private static boolean hasText(String value) { return value != null && !value.isBlank(); }

    private static String trimToNull(String value) { return hasText(value) ? value.trim() : null; }

    private static int bool(boolean value) { return value ? 1 : 0; }

    private static String nonce() {
        byte[] bytes = new byte[24];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static Instant instant(ResultSet rs, String column) throws java.sql.SQLException {
        Timestamp value = rs.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }

    private static Long nullableLong(ResultSet rs, String column) throws java.sql.SQLException {
        long value = rs.getLong(column);
        return rs.wasNull() ? null : value;
    }

    private static Integer nullableInt(ResultSet rs, String column) throws java.sql.SQLException {
        int value = rs.getInt(column);
        return rs.wasNull() ? null : value;
    }

    /* ── 行模型 ───────────────────────────────────────────────────────── */

    private record PlanRow(long id, long userId, String workspace, String environment, String planDigest,
                           int createCount, int updateCount, int deleteCount, int replaceCount, int changeCount,
                           boolean destroyDetected, boolean truncated, String terraformVersion,
                           Long stateSerial, String commitSha, String imageDigest, String releaseVersion,
                           Long rollbackOfReleaseId, String status, String approvalNonce, Long approvedBy,
                           Instant approvedAt, Instant createdAt, List<TerraformPlanAnalyzer.Change> changes) {}

    private record ApplyRow(long id, long planId, long userId, String workspace, String status,
                            String dispatchStatus, Instant dispatchedAt, String runTraceId, Integer exitCode,
                            Instant appliedAt, String verificationStatus, Instant verifiedAt,
                            String verificationDetail) {}

    private record ReleaseRow(long id, long userId, String workspace, String environment, String releaseVersion,
                              String commitSha, String imageDigest, long planId, long applyId, String direction,
                              String status, Instant appliedAt, Instant verifiedAt, Long previousReleaseId) {}

    private static final RowMapper<PlanRow> PLAN_MAPPER = (rs, rowNum) -> new PlanRow(
            rs.getLong("id"), rs.getLong("user_id"), rs.getString("workspace"), rs.getString("environment"),
            rs.getString("plan_digest"), rs.getInt("create_count"), rs.getInt("update_count"),
            rs.getInt("delete_count"), rs.getInt("replace_count"), rs.getInt("change_count"),
            rs.getInt("destroy_detected") != 0, rs.getInt("truncated") != 0, rs.getString("terraform_version"),
            nullableLong(rs, "state_serial"), rs.getString("commit_sha"), rs.getString("image_digest"),
            rs.getString("release_version"), nullableLong(rs, "rollback_of_release_id"), rs.getString("status"),
            rs.getString("approval_nonce"), nullableLong(rs, "approved_by"), instant(rs, "approved_at"),
            instant(rs, "created_at"), readChanges(rs.getString("plan_summary_json")));

    private static final RowMapper<ApplyRow> APPLY_MAPPER = (rs, rowNum) -> new ApplyRow(
            rs.getLong("id"), rs.getLong("plan_id"), rs.getLong("user_id"), rs.getString("workspace"),
            rs.getString("status"), rs.getString("dispatch_status"), instant(rs, "dispatched_at"),
            rs.getString("run_trace_id"), nullableInt(rs, "exit_code"), instant(rs, "applied_at"),
            rs.getString("verification_status"), instant(rs, "verified_at"), rs.getString("verification_detail"));

    private static final RowMapper<ReleaseRow> RELEASE_MAPPER = (rs, rowNum) -> new ReleaseRow(
            rs.getLong("id"), rs.getLong("user_id"), rs.getString("workspace"), rs.getString("environment"),
            rs.getString("release_version"), rs.getString("commit_sha"), rs.getString("image_digest"),
            rs.getLong("plan_id"), rs.getLong("apply_id"), rs.getString("direction"), rs.getString("status"),
            instant(rs, "applied_at"), instant(rs, "verified_at"), nullableLong(rs, "previous_release_id"));

    private static List<TerraformPlanAnalyzer.Change> readChanges(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            return JSON.readValue(json, new TypeReference<List<TerraformPlanAnalyzer.Change>>() {});
        } catch (Exception malformed) {
            return List.of();
        }
    }

    /* ── 公开视图 ─────────────────────────────────────────────────────── */

    public record PlanView(long id, String workspace, String environment, String planDigest,
                           int createCount, int updateCount, int deleteCount, int replaceCount, int changeCount,
                           boolean destroyDetected, boolean truncated, String terraformVersion,
                           Long stateSerial, String commitSha, String imageDigest, String releaseVersion,
                           Long rollbackOfReleaseId, String status, String approvalNonce, Long approvedBy,
                           Instant approvedAt, Instant createdAt, List<TerraformPlanAnalyzer.Change> changes) {}

    public record ApplyView(long id, long planId, String workspace, String status, String dispatchStatus,
                            Instant dispatchedAt, String runTraceId, Integer exitCode, Instant appliedAt,
                            String verificationStatus, Instant verifiedAt, String verificationDetail) {}

    public record ReleaseView(long id, String workspace, String environment, String releaseVersion,
                              String commitSha, String imageDigest, long planId, long applyId, String direction,
                              String status, Instant appliedAt, Instant verifiedAt, Long previousReleaseId) {}

    public record DriftView(String workspace, String status, boolean drifted, String reason,
                            String expectedCommit, String expectedImageDigest,
                            String actualCommit, String actualImageDigest,
                            Long latestPlanId, Long latestReleaseId) {}

    public record PlanRequest(String workspace, String environment, String planJson, String commitSha,
                              String imageDigest, String releaseVersion, Long rollbackOfReleaseId) {}

    public record Check(String name, boolean passed, String detail) {}
}
