package com.smartops.iac;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-12：计划脱敏、销毁识别、审批绑定、状态锁与并发变更、变更后验证、发布漂移与受控回滚。
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:iac_service;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class IacServiceIntegrationTest {

    private static final long OWNER = 101L;
    private static final String WORKSPACE = "prod-network";

    @Autowired JdbcTemplate jdbc;
    @Autowired IacService iac;
    @Autowired IacController controller;

    @BeforeEach
    void clean() {
        jdbc.update("DELETE FROM iac_release_record");
        jdbc.update("DELETE FROM iac_apply_record");
        jdbc.update("DELETE FROM iac_plan_record");
        jdbc.update("DELETE FROM operation_run_record");
    }

    @Test
    @DisplayName("计划分析：脱敏、识别销毁、摘要稳定")
    void planAnalysisRedactsAndDetectsDestroy() {
        TerraformPlanAnalyzer.Analysis analysis = iac.analyze(planJson(12, true, "top-secret-value"));

        assertThat(analysis.createCount()).isEqualTo(1);
        assertThat(analysis.deleteCount()).isEqualTo(1);
        assertThat(analysis.replaceCount()).isEqualTo(1);
        assertThat(analysis.destroyDetected()).isTrue();
        assertThat(analysis.stateSerial()).isEqualTo(12);
        assertThat(analysis.changes()).noneSatisfy(change ->
                assertThat(change.toString()).contains("top-secret-value"));
        assertThat(iac.analyze(planJson(12, true, "other-secret")).digest())
                .as("计划摘要只由结构与动作决定，不因属性值不同而漂移")
                .isEqualTo(analysis.digest());
        assertThat(iac.analyze(planJson(12, false, "x")).digest()).isNotEqualTo(analysis.digest());
        assertThat(controller.analyze(new IacController.AnalyzeRequest(planJson(12, true, "x")))
                .getData().destroyDetected()).isTrue();
    }

    @Test
    @DisplayName("销毁型计划必须显式确认；审批结果绑定摘要与审批码")
    void destroyPlanRequiresExplicitConfirmation() {
        IacService.PlanView plan = createPlan(12, true, "abc123", "sha256:image-1", null);

        assertThat(plan.status()).isEqualTo("PLANNED");
        assertThatThrownBy(() -> iac.approve(OWNER, plan.id(), false))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("IAC_DESTROY_NOT_CONFIRMED");

        IacService.PlanView approved = iac.approve(OWNER, plan.id(), true);
        assertThat(approved.status()).isEqualTo("APPROVED");
        assertThat(approved.approvalNonce()).isNotBlank();
        assertThat(approved.approvedBy()).isEqualTo(OWNER);
        assertThat(approved.approvedAt()).isNotNull();

        assertThatThrownBy(() -> iac.dispatch(OWNER, plan.id(), "wrong-nonce"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("IAC_APPROVAL_NONCE_MISMATCH");
    }

    @Test
    @DisplayName("SENT 与执行成功、验证通过分开记录；验证失败不得写成成功")
    void sentAppliedAndVerifiedAreRecordedSeparately() {
        IacService.PlanView plan = createPlan(3, false, "abc123", "sha256:image-1", null);
        iac.approve(OWNER, plan.id(), false);

        IacService.ApplyView dispatched = iac.dispatch(OWNER, plan.id(), planNonce(plan.id()));
        assertThat(dispatched.status()).isEqualTo("DISPATCHED");
        assertThat(dispatched.dispatchStatus()).isEqualTo("SENT");
        assertThat(dispatched.appliedAt()).isNull();
        assertThat(dispatched.verifiedAt()).isNull();

        insertRun("trace-iac-apply-1", "SUCCEEDED");
        IacService.ApplyView applied = iac.completeApply(OWNER, dispatched.id(), "trace-iac-apply-1", 0);
        assertThat(applied.status()).isEqualTo("APPLIED");
        assertThat(applied.appliedAt()).isNotNull();
        assertThat(applied.verificationStatus()).isEqualTo("UNVERIFIED");
        assertThat(applied.verifiedAt()).isNull();

        IacService.ApplyView failedVerification = iac.verify(OWNER, applied.id(),
                List.of(new IacService.Check("endpoint-health", false, "健康检查未通过"),
                        new IacService.Check("error-rate", true, null)));
        assertThat(failedVerification.verificationStatus()).isEqualTo("VERIFICATION_FAILED");
        assertThat(failedVerification.verifiedAt()).isNull();
        assertThat(failedVerification.verificationDetail()).contains("endpoint-health=false");
        assertThat(iac.releases(OWNER, WORKSPACE)).singleElement()
                .satisfies(release -> assertThat(release.status()).isEqualTo("VERIFICATION_FAILED"));
    }

    @Test
    @DisplayName("验证全部通过才记 VERIFIED，并回写发布历史")
    void verificationRequiresAllChecksAndRealEvidence() {
        IacService.ApplyView applied = appliedPlan(4, "trace-iac-ok", "SUCCEEDED", 0);

        assertThatThrownBy(() -> iac.verify(OWNER, applied.id(), List.of()))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("IAC_VERIFICATION_EVIDENCE_REQUIRED");

        IacService.ApplyView verified = iac.verify(OWNER, applied.id(),
                List.of(new IacService.Check("http-probe", true, "200"),
                        new IacService.Check("asset-count", true, "42")));
        assertThat(verified.verificationStatus()).isEqualTo("VERIFIED");
        assertThat(verified.verifiedAt()).isNotNull();
        assertThat(iac.releases(OWNER, WORKSPACE)).singleElement().satisfies(release -> {
            assertThat(release.status()).isEqualTo("VERIFIED");
            assertThat(release.verifiedAt()).isNotNull();
            assertThat(release.commitSha()).isEqualTo("abc123");
            assertThat(release.imageDigest()).isEqualTo("sha256:image-1");
        });
    }

    @Test
    @DisplayName("缺运行证据或运行失败时不记执行成功，也不生成发布")
    void applyRequiresRealRunEvidence() {
        IacService.PlanView plan = createPlan(1, false, "abc123", "sha256:image-1", null);
        iac.approve(OWNER, plan.id(), false);
        IacService.ApplyView dispatched = iac.dispatch(OWNER, plan.id(), planNonce(plan.id()));

        assertThatThrownBy(() -> iac.completeApply(OWNER, dispatched.id(), "trace-missing", 0))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("IAC_RUN_EVIDENCE_INVALID");

        insertRun("trace-iac-failed", "FAILED");
        IacService.ApplyView failed = iac.completeApply(OWNER, dispatched.id(), "trace-iac-failed", 1);
        assertThat(failed.status()).isEqualTo("FAILED");
        assertThat(failed.appliedAt()).isNull();
        assertThat(iac.releases(OWNER, WORKSPACE)).isEmpty();
        assertThat(iac.detail(OWNER, plan.id()).status()).isEqualTo("FAILED");
    }

    @Test
    @DisplayName("同一 workspace 有下发中的变更时拒绝并发；过期计划不得下发")
    void stateLockAndStalePlanAreRejected() {
        IacService.PlanView first = createPlan(2, false, "abc123", "sha256:image-1", null);
        iac.approve(OWNER, first.id(), false);
        IacService.ApplyView firstApply = iac.dispatch(OWNER, first.id(), planNonce(first.id()));

        IacService.PlanView second = createPlan(5, false, "def456", "sha256:image-2", null);
        iac.approve(OWNER, second.id(), false);
        assertThatThrownBy(() -> iac.dispatch(OWNER, second.id(), planNonce(second.id())))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("IAC_STATE_LOCKED");

        insertRun("trace-iac-first", "SUCCEEDED");
        iac.completeApply(OWNER, firstApply.id(), "trace-iac-first", 0);

        // 第一份计划执行完成后，又出现了第三份更新计划：第二份已过期。
        createPlan(9, false, "ghi789", "sha256:image-3", null);
        assertThatThrownBy(() -> iac.dispatch(OWNER, second.id(), planNonce(second.id())))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("IAC_PLAN_STALE");
    }

    @Test
    @DisplayName("漂移分析比较期望与实际；回滚计划绑定目标发布的 commit/镜像")
    void driftAndRollbackBindToApprovedPlan() {
        IacService.ApplyView applied = appliedPlanVerified(7, "trace-iac-drift", "v1.2.0");

        IacService.DriftView inSync = iac.drift(OWNER, WORKSPACE);
        assertThat(inSync.status()).isEqualTo("IN_SYNC");
        assertThat(inSync.drifted()).isFalse();

        IacService.PlanView pending = createPlan(8, false, "new-commit", "sha256:image-new", "v1.3.0");
        IacService.DriftView drifted = iac.drift(OWNER, WORKSPACE);
        assertThat(drifted.status()).isEqualTo("DRIFT");
        assertThat(drifted.drifted()).isTrue();
        assertThat(drifted.expectedCommit()).isEqualTo("new-commit");
        assertThat(drifted.actualCommit()).isEqualTo("abc123");

        long releaseId = iac.releases(OWNER, WORKSPACE).get(0).id();
        assertThatThrownBy(() -> createPlan(9, false, "wrong-commit", "sha256:image-1", null, releaseId))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("IAC_ROLLBACK_TARGET_MISMATCH");

        IacService.PlanView rollback = createPlan(9, false, "abc123", "sha256:image-1", "v1.2.1", releaseId);
        iac.approve(OWNER, rollback.id(), false);
        IacService.ApplyView dispatched = iac.dispatch(OWNER, rollback.id(), planNonce(rollback.id()));
        insertRun("trace-iac-rollback", "SUCCEEDED");
        iac.completeApply(OWNER, dispatched.id(), "trace-iac-rollback", 0);
        iac.verify(OWNER, dispatched.id(), List.of(new IacService.Check("rollback-probe", true, "ok")));

        IacService.ReleaseView latest = iac.releases(OWNER, WORKSPACE).get(0);
        assertThat(latest.direction()).isEqualTo("ROLLBACK");
        assertThat(latest.previousReleaseId()).isEqualTo(releaseId);
        assertThat(latest.commitSha()).isEqualTo("abc123");
        assertThat(pending.id()).isNotEqualTo(applied.planId());
    }

    @Test
    @DisplayName("非归属用户看不到计划")
    void plansAreOwnerScoped() {
        IacService.PlanView plan = createPlan(1, false, "abc123", "sha256:image-1", null);
        assertThatThrownBy(() -> iac.detail(OWNER + 1, plan.id()))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("IAC_PLAN_NOT_FOUND");
    }

    /* ── 夹具 ─────────────────────────────────────────────────────────── */

    private IacService.PlanView createPlan(long serial, boolean destroy, String commit, String imageDigest,
                                           String releaseVersion) {
        return createPlan(serial, destroy, commit, imageDigest, releaseVersion, null);
    }

    private IacService.PlanView createPlan(long serial, boolean destroy, String commit, String imageDigest,
                                           String releaseVersion, Long rollbackOfReleaseId) {
        return iac.plan(OWNER, new IacService.PlanRequest(WORKSPACE, "prod",
                planJson(serial, destroy, "secret-" + serial), commit, imageDigest, releaseVersion,
                rollbackOfReleaseId));
    }

    private IacService.ApplyView appliedPlan(long serial, String traceId, String runStatus, int exitCode) {
        IacService.PlanView plan = createPlan(serial, false, "abc123", "sha256:image-1", "v1.2.0");
        iac.approve(OWNER, plan.id(), false);
        IacService.ApplyView dispatched = iac.dispatch(OWNER, plan.id(), planNonce(plan.id()));
        insertRun(traceId, runStatus);
        return iac.completeApply(OWNER, dispatched.id(), traceId, exitCode);
    }

    private IacService.ApplyView appliedPlanVerified(long serial, String traceId, String releaseVersion) {
        IacService.PlanView plan = createPlan(serial, false, "abc123", "sha256:image-1", releaseVersion);
        iac.approve(OWNER, plan.id(), false);
        IacService.ApplyView dispatched = iac.dispatch(OWNER, plan.id(), planNonce(plan.id()));
        insertRun(traceId, "SUCCEEDED");
        IacService.ApplyView applied = iac.completeApply(OWNER, dispatched.id(), traceId, 0);
        return iac.verify(OWNER, applied.id(), List.of(new IacService.Check("probe", true, "ok")));
    }

    private String planNonce(long planId) {
        return iac.detail(OWNER, planId).approvalNonce();
    }

    private void insertRun(String traceId, String status) {
        jdbc.update("""
                INSERT INTO operation_run_record (trace_id,user_id,runtime_id,tool_id,status,started_at,ended_at)
                VALUES (?,?,?,?,?,?,?)
                """, traceId, OWNER, "runtime-1", "terraform-apply", status,
                Timestamp.from(Instant.now().minusSeconds(30)), Timestamp.from(Instant.now()));
    }

    private static String planJson(long serial, boolean destroy, String secretValue) {
        String delete = destroy
                ? """
                  ,{"address":"aws_s3_bucket.old","type":"aws_s3_bucket","name":"old",
                    "change":{"actions":["delete"],"before":{"secret":"%s"}}}
                  ,{"address":"aws_security_group.sg","type":"aws_security_group","name":"sg",
                    "change":{"actions":["delete","create"]}}
                  """.formatted(secretValue)
                : "";
        return """
                {
                  "format_version": "1.0",
                  "terraform_version": "1.6.6",
                  "prior_state": {"serial": %d, "lineage": "lineage-%d"},
                  "resource_changes": [
                    {"address":"aws_instance.web","type":"aws_instance","name":"web",
                     "change":{"actions":["create"],"after":{"password":"%s"}}}
                    %s
                  ]
                }
                """.formatted(serial, serial, secretValue, delete);
    }
}
