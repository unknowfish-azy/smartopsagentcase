package com.smartops.experiment;

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
 * OPS-16：评估字段完整性、停止条件、恢复证据、卸载留证与引入门槛。
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:experiment_service;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class ExperimentServiceIntegrationTest {

    private static final long OWNER = 141L;
    private static final long OTHER = 142L;

    @Autowired JdbcTemplate jdbc;
    @Autowired ExperimentService experiments;

    @BeforeEach
    void clean() {
        jdbc.update("DELETE FROM platform_experiment_drill");
        jdbc.update("DELETE FROM platform_experiment_evaluation");
        jdbc.update("DELETE FROM backup_drill_record");
        jdbc.update("DELETE FROM backup_recovery_set");
    }

    @Test
    @DisplayName("评估必须写清必要性/触发条件/控制面/权限/兼容性/开销/卸载步骤，同组件不可重复登记")
    void evaluationRequiresAllDecisionFields() {
        long id = create("CHAOSBLADE");
        assertThat(experiments.listEvaluations(OWNER)).singleElement().satisfies(view -> {
            assertThat(view.id()).isEqualTo(id);
            assertThat(view.component()).isEqualTo("CHAOSBLADE");
            assertThat(view.canAdopt()).isFalse();
            assertThat(view.drillCount()).isZero();
            assertThat(view.exitVerifiedAt()).isNull();
        });

        assertThatThrownBy(() -> create("CHAOSBLADE"))
                .isInstanceOf(BusinessException.class).hasMessageContaining("EXPERIMENT_EVALUATION_EXISTS");
        assertThatThrownBy(() -> experiments.createEvaluation(OWNER, new ExperimentService.EvaluationInput(
                "kubeflow", "标题", "必要性", "触发", "控制面", "权限", "兼容", "开销", "卸载")))
                .isInstanceOf(BusinessException.class).hasMessageContaining("EXPERIMENT_COMPONENT_UNSUPPORTED");
        assertThatThrownBy(() -> experiments.createEvaluation(OWNER, new ExperimentService.EvaluationInput(
                "KARMADA", "标题", "必要性", "触发", "控制面", "权限", "兼容", "开销", " ")))
                .isInstanceOf(BusinessException.class).hasMessageContaining("EXPERIMENT_UNINSTALL_REQUIRED");
    }

    @Test
    @DisplayName("演练只接受隔离模式，必须先声明停止条件，时间必须有序")
    void drillRequiresIsolationAndStopConditions() {
        long id = create("KARMADA");
        Instant start = Instant.parse("2026-11-06T02:00:00Z");

        assertThatThrownBy(() -> experiments.recordDrill(OWNER, id, new ExperimentService.DrillInput(
                "PRODUCTION", "cluster-a", start, start.plusSeconds(3600), List.of("错误率>5%"),
                false, null, "recovered", null)))
                .isInstanceOf(BusinessException.class).hasMessageContaining("EXPERIMENT_DRILL_MODE_INVALID");
        assertThatThrownBy(() -> experiments.recordDrill(OWNER, id, new ExperimentService.DrillInput(
                "ISOLATED", "cluster-a", start, start.plusSeconds(3600), List.of("  "),
                false, null, "recovered", null)))
                .isInstanceOf(BusinessException.class).hasMessageContaining("EXPERIMENT_STOP_CONDITIONS_REQUIRED");
        assertThatThrownBy(() -> experiments.recordDrill(OWNER, id, new ExperimentService.DrillInput(
                "ISOLATED", "cluster-a", start, start, List.of("错误率>5%"),
                false, null, "recovered", null)))
                .isInstanceOf(BusinessException.class).hasMessageContaining("EXPERIMENT_DRILL_TIME_INVALID");
        assertThatThrownBy(() -> experiments.recordDrill(OTHER, id, complete(start)))
                .isInstanceOf(BusinessException.class).hasMessageContaining("EXPERIMENT_EVALUATION_NOT_FOUND");
    }

    @Test
    @DisplayName("停止触发却无证据判 FAILED，缺恢复证据判 UNVERIFIED，证据齐全才 VERIFIED")
    void drillResultReflectsEvidence() {
        long id = create("CHAOSBLADE");
        Instant start = Instant.parse("2026-11-06T02:00:00Z");

        ExperimentService.DrillView verified = experiments.recordDrill(OWNER, id, complete(start));
        assertThat(verified.result()).isEqualTo("VERIFIED");
        assertThat(verified.gaps()).isEmpty();
        assertThat(verified.stopConditions()).containsExactly("错误率>5%", "P99>2s");
        assertThat(verified.recoveryEvidence()).isEqualTo("slo-window:2026-11-06T02:00Z/03:00Z");

        ExperimentService.DrillView failed = experiments.recordDrill(OWNER, id, new ExperimentService.DrillInput(
                "ISOLATED", "cluster-a", start, start.plusSeconds(3600), List.of("错误率>5%"),
                true, null, "slo-window:2026-11-06T02:00Z/03:00Z", null));
        assertThat(failed.result()).isEqualTo("FAILED");
        assertThat(failed.gaps()).containsExactly("STOP_EVIDENCE_MISSING");

        ExperimentService.DrillView unverified = experiments.recordDrill(OWNER, id, new ExperimentService.DrillInput(
                "ISOLATED", "cluster-a", start, start.plusSeconds(3600), List.of("错误率>5%"),
                false, null, null, null));
        assertThat(unverified.result()).isEqualTo("UNVERIFIED");
        assertThat(unverified.gaps()).containsExactly("RECOVERY_EVIDENCE_MISSING");

        ExperimentService.DrillView stopped = experiments.recordDrill(OWNER, id, new ExperimentService.DrillInput(
                "ISOLATED", "cluster-a", start, start.plusSeconds(3600), List.of("错误率>5%"),
                true, "告警 INC-1 触发后 30s 内停止派发", null, null));
        assertThat(stopped.result()).isEqualTo("UNVERIFIED");
        assertThat(stopped.gaps()).containsExactly("RECOVERY_EVIDENCE_MISSING");
    }

    @Test
    @DisplayName("恢复证据可引用 OPS-13 备份演练，但只有已验证且属于本用户的才作数")
    void recoveryMayReferenceVerifiedBackupDrill() {
        long id = create("KUBEEDGE");
        Instant start = Instant.parse("2026-11-06T02:00:00Z");
        long verifiedBackup = backupDrill(OWNER, "VERIFIED", "set-a");
        long unverifiedBackup = backupDrill(OWNER, "FAILED", "set-b");
        long foreignBackup = backupDrill(OTHER, "VERIFIED", "set-c");

        ExperimentService.DrillView accepted = experiments.recordDrill(OWNER, id,
                withBackup(start, verifiedBackup));
        assertThat(accepted.result()).isEqualTo("VERIFIED");
        assertThat(accepted.backupDrillId()).isEqualTo(verifiedBackup);

        ExperimentService.DrillView failedBackup = experiments.recordDrill(OWNER, id,
                withBackup(start, unverifiedBackup));
        assertThat(failedBackup.result()).isEqualTo("UNVERIFIED");
        assertThat(failedBackup.gaps()).contains("BACKUP_DRILL_NOT_VERIFIED");

        ExperimentService.DrillView foreign = experiments.recordDrill(OWNER, id,
                withBackup(start, foreignBackup));
        assertThat(foreign.result()).isEqualTo("UNVERIFIED");
        assertThat(foreign.gaps()).contains("BACKUP_DRILL_NOT_VERIFIED");
    }

    @Test
    @DisplayName("只有 VERIFIED 演练加卸载留证才允许引入；卸载证据不能为空")
    void adoptionGateRequiresDrillAndExitEvidence() {
        long id = create("CHAOSBLADE");
        Instant start = Instant.parse("2026-11-06T02:00:00Z");

        experiments.recordDrill(OWNER, id, complete(start));
        assertThat(experiments.listEvaluations(OWNER)).singleElement()
                .satisfies(view -> assertThat(view.canAdopt()).isFalse());

        assertThatThrownBy(() -> experiments.recordExit(OWNER, id, "  "))
                .isInstanceOf(BusinessException.class).hasMessageContaining("EXPERIMENT_EXIT_EVIDENCE_REQUIRED");

        ExperimentService.EvaluationView exited = experiments.recordExit(OWNER, id,
                "helm uninstall karmada && kubectl get ns 无残留");
        assertThat(exited.exitVerifiedAt()).isNotNull();
        assertThat(exited.exitEvidence()).contains("helm uninstall");
        assertThat(exited.canAdopt()).isTrue();

        long kubeedge = create("KUBEEDGE");
        experiments.recordExit(OWNER, kubeedge, "已确认无残留 CRD");
        ExperimentService.EvaluationView noDrill = experiments.listEvaluations(OWNER).stream()
                .filter(view -> view.id() == kubeedge).findFirst().orElseThrow();
        assertThat(noDrill.canAdopt()).isFalse();
    }

    @Test
    @DisplayName("评估列表按组件排序且按用户隔离")
    void evaluationsAreSortedAndScoped() {
        create("KARMADA");
        create("CHAOSBLADE");

        assertThat(experiments.listEvaluations(OWNER))
                .extracting(ExperimentService.EvaluationView::component)
                .containsExactly("CHAOSBLADE", "KARMADA");
        assertThat(experiments.listEvaluations(OTHER)).isEmpty();
    }

    private long create(String component) {
        return experiments.createEvaluation(OWNER, new ExperimentService.EvaluationInput(
                component, component + " 引入评估", "现有多集群/边缘需求尚未成立",
                "同一业务需要跨集群故障迁移且人工切换超过 30 分钟",
                "需额外控制面与高可用部署", "需集群管理员与跨集群网络权限",
                "需验证内核版本、CRD 与 CNI 兼容性", "需 3 台控制面与跨集群带宽",
                "按文档卸载 CRD、命名空间与代理，确认无残留")).id();
    }

    private ExperimentService.DrillInput complete(Instant start) {
        return new ExperimentService.DrillInput("ISOLATED", "cluster-a", start, start.plusSeconds(3600),
                List.of("错误率>5%", "P99>2s"), false, null,
                "slo-window:2026-11-06T02:00Z/03:00Z", null);
    }

    private ExperimentService.DrillInput withBackup(Instant start, long backupDrillId) {
        return new ExperimentService.DrillInput("ISOLATED", "cluster-a", start, start.plusSeconds(3600),
                List.of("错误率>5%"), false, null, null, backupDrillId);
    }

    private long backupDrill(long userId, String result, String setName) {
        jdbc.update("""
                INSERT INTO backup_recovery_set (user_id,name,environment,components,retention_days,offsite_required)
                VALUES (?,?,?,?,?,?)
                """, userId, setName, "test", "DATABASE", 14, 1);
        long setId = jdbc.queryForObject("SELECT id FROM backup_recovery_set WHERE user_id=? AND name=?",
                Long.class, userId, setName);
        Instant start = Instant.parse("2026-11-06T01:00:00Z");
        jdbc.update("""
                INSERT INTO backup_drill_record
                  (set_id,mode,started_at,finished_at,expected_count,restored_count,hash_verified,
                   reference_check,key_query_check,result)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """, setId, "ISOLATED_RESTORE", Timestamp.from(start), Timestamp.from(start.plusSeconds(3600)),
                10L, 10L, 1, "PASS", "PASS", result);
        return jdbc.queryForObject("SELECT MAX(id) FROM backup_drill_record WHERE set_id=?", Long.class, setId);
    }
}
