package com.smartops.observability;

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
 * OPS-10：SLI/SLO 的口径、分母与数据质量必须能复核；恢复判定只认业务证据。
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:slo_service;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        // 用部署声明区分真实数据与夹具：测试上下文显式声明 FIXTURE，接口必须如实标注。
        "smartops.observability.data-source=FIXTURE",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000",
        "smartops.sentinel.recovery.initial-delay-ms=86400000",
        "smartops.sentinel.dead-letter.initial-delay-ms=86400000"
})
class SloServiceIntegrationTest {

    private static final long OWNER = 91L;

    @Autowired JdbcTemplate jdbc;
    @Autowired SloService slo;
    @Autowired SloController controller;

    @BeforeEach
    void clean() {
        jdbc.update("DELETE FROM recovery_observation_record");
        jdbc.update("DELETE FROM recovery_receipt_record");
        jdbc.update("DELETE FROM recovery_contract_record");
        jdbc.update("DELETE FROM operation_run_record");
        jdbc.update("DELETE FROM sentinel_task");
    }

    @Test
    @DisplayName("三个 SLI 的分子/分母/窗口/状态与数据质量都可复核")
    void evaluatesSliFromPlatformFacts() {
        Instant now = Instant.now();
        insertRuns(now, 27, 3);
        insertTasks(now, 6, 1, 1);
        long contractId = insertContract(now, 1, "target-a", "digest-a");
        insertReceipt(contractId, "r-ok-1", "VERIFIED", "ACTIVE", now.plusSeconds(3600));
        insertReceipt(contractId, "r-ok-2", "VERIFIED", "ACTIVE", now.plusSeconds(3600));
        insertReceipt(contractId, "r-ok-3", "VERIFIED", "ACTIVE", now.plusSeconds(3600));
        insertReceipt(contractId, "r-bad-1", "CONTRADICTED", "NOT_ISSUED", null);

        List<SloService.Evaluation> evaluations = slo.evaluate(24);

        SloService.Evaluation execution = byId(evaluations, "execution_success");
        assertThat(execution.denominator()).isEqualTo(30);
        assertThat(execution.numerator()).isEqualTo(27);
        assertThat(execution.value()).isEqualTo(0.9);
        assertThat(execution.objective()).isEqualTo(0.99);
        assertThat(execution.status()).isEqualTo("EXHAUSTED");
        assertThat(execution.dataQuality()).isEqualTo("REAL");
        assertThat(execution.dataSource()).isEqualTo("FIXTURE");
        assertThat(execution.formula()).contains("SUCCEEDED").contains("已结束运行数");

        SloService.Evaluation freshness = byId(evaluations, "collection_freshness");
        assertThat(freshness.denominator()).isEqualTo(7);
        assertThat(freshness.numerator()).isEqualTo(6);
        assertThat(freshness.status()).isEqualTo("EXHAUSTED");
        assertThat(freshness.dataQuality()).isEqualTo("REAL");

        SloService.Evaluation recovery = byId(evaluations, "recovery_verification");
        assertThat(recovery.denominator()).isEqualTo(4);
        assertThat(recovery.numerator()).isEqualTo(3);
        assertThat(recovery.burnRate()).isEqualTo(5.0);
        assertThat(recovery.dataQuality()).isEqualTo("DEGRADED");

        assertThat(controller.slo(24).getData()).hasSize(3);
    }

    @Test
    @DisplayName("无样本时是 NO_DATA/INSUFFICIENT，不得写成达标")
    void noSamplesIsNotSuccess() {
        List<SloService.Evaluation> evaluations = slo.evaluate(24);

        assertThat(evaluations).allSatisfy(evaluation -> {
            assertThat(evaluation.denominator()).isZero();
            assertThat(evaluation.value()).isNull();
            assertThat(evaluation.status()).isEqualTo("NO_DATA");
            assertThat(evaluation.dataQuality()).isEqualTo("INSUFFICIENT");
        });
    }

    @Test
    @DisplayName("窗口越界直接拒绝")
    void rejectsInvalidWindow() {
        assertThatThrownBy(() -> slo.evaluate(0)).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> slo.evaluate(169)).isInstanceOf(BusinessException.class);
    }

    @Test
    @DisplayName("恢复判定：仅 VERIFIED+ACTIVE 且未过期才返回 RECOVERED")
    void judgesRecoveryFromIndependentEvidence() {
        Instant now = Instant.now();
        long runId = insertRun("trace-recovered", "SUCCEEDED", now);
        long recovered = insertContract(now, runId, "target-a", "digest-a");
        insertReceipt(recovered, "r-1", "VERIFIED", "ACTIVE", now.plusSeconds(3600));
        insertObservation(recovered, "o-1", now.minusSeconds(60));
        insertObservation(recovered, "o-2", now.minusSeconds(30));

        SloService.RecoveryVerdict verdict = slo.judgeRecovery(recovered, OWNER);
        assertThat(verdict.recovered()).isTrue();
        assertThat(verdict.state()).isEqualTo("RECOVERED");
        assertThat(verdict.traceId()).isEqualTo("trace-recovered");
        assertThat(verdict.observationCount()).isEqualTo(2);
        assertThat(verdict.receiptId()).isEqualTo("r-1");
        assertThat(controller.recovery(recovered, OWNER).getData().recovered()).isTrue();
    }

    @Test
    @DisplayName("过期/未通过/失效/无回执都不算恢复")
    void neverClaimsRecoveryWithoutValidEvidence() {
        Instant now = Instant.now();
        long expired = insertContract(now, insertRun("trace-expired", "SUCCEEDED", now), "t1", "d1");
        insertReceipt(expired, "r-exp", "VERIFIED", "ACTIVE", now.minusSeconds(60));
        long contradicted = insertContract(now, insertRun("trace-bad", "FAILED", now), "t2", "d2");
        insertReceipt(contradicted, "r-bad", "CONTRADICTED", "NOT_ISSUED", null);
        long invalidated = insertContract(now, insertRun("trace-inv", "SUCCEEDED", now), "t3", "d3");
        insertReceipt(invalidated, "r-inv", "VERIFIED", "INVALIDATED", now.plusSeconds(3600));
        long noReceipt = insertContract(now, insertRun("trace-none", "SUCCEEDED", now), "t4", "d4");

        assertThat(slo.judgeRecovery(expired, OWNER).state()).isEqualTo("STALE");
        assertThat(slo.judgeRecovery(contradicted, OWNER).state()).isEqualTo("NOT_RECOVERED");
        assertThat(slo.judgeRecovery(invalidated, OWNER).state()).isEqualTo("INVALIDATED");
        SloService.RecoveryVerdict unknown = slo.judgeRecovery(noReceipt, OWNER);
        assertThat(unknown.state()).isEqualTo("UNKNOWN");
        assertThat(unknown.recovered()).isFalse();
        assertThat(unknown.explanation()).contains("告警关闭不等于");
    }

    @Test
    @DisplayName("非归属用户看不到契约，避免越权读取恢复结论")
    void recoveryVerdictIsOwnerScoped() {
        Instant now = Instant.now();
        long contractId = insertContract(now, insertRun("trace-own", "SUCCEEDED", now), "t1", "d1");

        assertThatThrownBy(() -> slo.judgeRecovery(contractId, 92L))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("RECOVERY_CONTRACT_NOT_FOUND");
    }

    @Test
    @DisplayName("未声明的数据来源标 UNKNOWN，不冒充真实")
    void unknownDataSourceIsNotPretendedReal() {
        SloService unknown = new SloService(jdbc, "mars");
        assertThat(unknown.evaluate(24)).allSatisfy(evaluation ->
                assertThat(evaluation.dataSource()).isEqualTo("UNKNOWN"));
    }

    /* ── 夹具 ─────────────────────────────────────────────────────────── */

    private SloService.Evaluation byId(List<SloService.Evaluation> evaluations, String id) {
        return evaluations.stream().filter(evaluation -> evaluation.id().equals(id)).findFirst().orElseThrow();
    }

    private void insertRuns(Instant now, int succeeded, int failed) {
        for (int i = 0; i < succeeded + failed; i++) {
            insertRun("trace-" + i, i < succeeded ? "SUCCEEDED" : "FAILED", now.minusSeconds(3600));
        }
    }

    private long insertRun(String traceId, String status, Instant startedAt) {
        jdbc.update("""
                INSERT INTO operation_run_record (trace_id,user_id,runtime_id,tool_id,status,started_at,ended_at)
                VALUES (?,?,?,?,?,?,?)
                """, traceId, OWNER, "runtime-1", "tool-1", status,
                Timestamp.from(startedAt), Timestamp.from(startedAt.plusSeconds(10)));
        return jdbc.queryForObject("SELECT id FROM operation_run_record WHERE trace_id=?", Long.class, traceId);
    }

    private void insertTasks(Instant now, int fresh, int stale, int disabled) {
        int total = fresh + stale + disabled;
        for (int i = 0; i < total; i++) {
            boolean enabled = i < fresh + stale;
            Timestamp lastSeen = i < fresh ? Timestamp.from(now.minusSeconds(30))
                    : (enabled ? Timestamp.from(now.minusSeconds(3600)) : null);
            jdbc.update("""
                    INSERT INTO sentinel_task (user_id,name,kind,target,interval_sec,enabled,last_seen_at)
                    VALUES (?,?,?,?,?,?,?)
                    """, OWNER, "task-" + i, "agent", "runtime-1", 60, enabled ? 1 : 0, lastSeen);
        }
    }

    private long insertContract(Instant now, long runId, String targetId, String digest) {
        String contractJson = "{\"id\":\"c-" + digest + "\"}";
        jdbc.update("""
                INSERT INTO recovery_contract_record
                    (contract_id,contract_version,run_id,owner_user_id,idempotency_key,scope,target_id,
                     expected_revision,digest,contract_json,claim_json,expires_after_ms,valid_from)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, "c-" + digest, "recovery-contract/v1", runId, OWNER, "idem-" + digest, "host",
                targetId, "r1", digest, contractJson, "{}", 600000L, now.toString());
        return jdbc.queryForObject("SELECT id FROM recovery_contract_record WHERE idempotency_key=?",
                Long.class, "idem-" + digest);
    }

    private void insertReceipt(long contractId, String receiptId, String verdict, String state, Instant validUntil) {
        String issuedAt = "VERIFIED".equals(verdict) ? Instant.now().minusSeconds(30).toString() : null;
        jdbc.update("""
                INSERT INTO recovery_receipt_record
                    (contract_record_id,receipt_id,run_id,verification_round,verdict,receipt_state,issued_at,
                     valid_until,evidence_snapshot_digest,policy_version,receipt_json,obligation_results_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, contractId, receiptId, "run-1", 1, verdict, state, issuedAt,
                validUntil == null ? null : validUntil.toString(), "sha256:abc", "recovery-policy/v1",
                "{}", "[]");
    }

    private void insertObservation(long contractId, String observationId, Instant observedAt) {
        jdbc.update("""
                INSERT INTO recovery_observation_record
                    (contract_record_id,observation_id,run_id,verification_round,collector_id,probe_id,
                     source_group,observed_at,binding_revision,sequence)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """, contractId, observationId, "run-1", 1, "collector", "probe", "group-1",
                observedAt.toString(), "r1", 1);
    }
}
