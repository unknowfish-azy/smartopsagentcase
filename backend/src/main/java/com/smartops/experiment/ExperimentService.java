package com.smartops.experiment;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * OPS-16：多集群、边缘与故障演练的可退出评估。
 *
 * <p>本服务不执行任何集群变更，也不替代既有 Run / 审批 / 审计体系：
 * 它只要求引入前把必要性、业务触发条件、额外控制面、权限、兼容性、开销与卸载步骤写清楚，
 * 并用"先声明停止条件、再留恢复证据"的隔离演练证明可退出。
 * 没有 VERIFIED 演练与卸载留证时，{@code canAdopt} 恒为 false。</p>
 */
@Service
public class ExperimentService {

    /** 只评估社区项目，不把厂商独占产品当作同类替身。 */
    public static final Set<String> COMPONENTS = Set.of("KARMADA", "KUBEEDGE", "CHAOSBLADE");

    private static final String MODE_ISOLATED = "ISOLATED";
    private static final ObjectMapper JSON = new ObjectMapper();

    private final JdbcTemplate jdbc;

    public ExperimentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /* ── 评估登记 ─────────────────────────────────────────────────────── */

    public EvaluationView createEvaluation(long userId, EvaluationInput input) {
        if (input == null) throw new BusinessException(400, "EXPERIMENT_EVALUATION_REQUIRED: 缺少评估内容");
        String component = requireText(input.component(), "EXPERIMENT_COMPONENT_REQUIRED: 缺少组件")
                .toUpperCase(Locale.ROOT);
        if (!COMPONENTS.contains(component)) {
            throw new BusinessException(400, "EXPERIMENT_COMPONENT_UNSUPPORTED: 仅评估 KARMADA/KUBEEDGE/CHAOSBLADE");
        }
        String title = requireText(input.title(), "EXPERIMENT_TITLE_REQUIRED: 缺少评估标题");
        String necessity = requireText(input.necessity(), "EXPERIMENT_NECESSITY_REQUIRED: 缺少必要性说明");
        String trigger = requireText(input.businessTrigger(),
                "EXPERIMENT_TRIGGER_REQUIRED: 缺少业务触发条件");
        String controlPlane = requireText(input.controlPlane(),
                "EXPERIMENT_CONTROL_PLANE_REQUIRED: 缺少额外控制面说明");
        String permissions = requireText(input.permissions(), "EXPERIMENT_PERMISSIONS_REQUIRED: 缺少权限影响说明");
        String compatibility = requireText(input.compatibility(),
                "EXPERIMENT_COMPATIBILITY_REQUIRED: 缺少内核/集群兼容性说明");
        String costNote = requireText(input.costNote(), "EXPERIMENT_COST_REQUIRED: 缺少开销说明");
        String uninstall = requireText(input.uninstallSteps(), "EXPERIMENT_UNINSTALL_REQUIRED: 缺少卸载步骤");

        Integer exists = jdbc.query("SELECT id FROM platform_experiment_evaluation WHERE user_id=? AND component=?",
                rs -> rs.next() ? rs.getInt(1) : null, userId, component);
        if (exists != null) {
            throw new BusinessException(409, "EXPERIMENT_EVALUATION_EXISTS: 该组件的评估已存在 " + component);
        }
        jdbc.update("""
                INSERT INTO platform_experiment_evaluation
                  (user_id,component,title,necessity,business_trigger,control_plane,permissions,
                   compatibility,cost_note,uninstall_steps,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, userId, component, title, necessity, trigger, controlPlane, permissions,
                compatibility, costNote, uninstall, Timestamp.from(Instant.now()));
        long id = jdbc.queryForObject(
                "SELECT id FROM platform_experiment_evaluation WHERE user_id=? AND component=?",
                Long.class, userId, component);
        return view(userId, requireEvaluation(userId, id));
    }

    public List<EvaluationView> listEvaluations(long userId) {
        List<EvaluationRow> rows = jdbc.query("""
                SELECT * FROM platform_experiment_evaluation WHERE user_id=? ORDER BY component
                """, EVALUATION_MAPPER, userId);
        List<EvaluationView> views = new ArrayList<>();
        for (EvaluationRow row : rows) views.add(view(userId, row));
        return List.copyOf(views);
    }

    /* ── 隔离演练 ─────────────────────────────────────────────────────── */

    public DrillView recordDrill(long userId, long evaluationId, DrillInput input) {
        requireEvaluation(userId, evaluationId);
        if (input == null) throw new BusinessException(400, "EXPERIMENT_DRILL_REQUIRED: 缺少演练内容");
        String mode = requireText(input.mode(), "EXPERIMENT_DRILL_MODE_REQUIRED: 缺少演练模式")
                .toUpperCase(Locale.ROOT);
        if (!MODE_ISOLATED.equals(mode)) {
            throw new BusinessException(400, "EXPERIMENT_DRILL_MODE_INVALID: 只接受 ISOLATED 隔离演练");
        }
        String scope = requireText(input.scope(), "EXPERIMENT_DRILL_SCOPE_REQUIRED: 缺少演练范围");
        Instant startedAt = requireInstant(input.startedAt(), "EXPERIMENT_DRILL_STARTED_AT_REQUIRED: 缺少开始时间");
        Instant finishedAt = requireInstant(input.finishedAt(), "EXPERIMENT_DRILL_FINISHED_AT_REQUIRED: 缺少结束时间");
        if (!finishedAt.isAfter(startedAt)) {
            throw new BusinessException(400, "EXPERIMENT_DRILL_TIME_INVALID: 结束时间必须晚于开始时间");
        }
        List<String> stopConditions = normalizeList(input.stopConditions());
        if (stopConditions.isEmpty()) {
            throw new BusinessException(400, "EXPERIMENT_STOP_CONDITIONS_REQUIRED: 必须先声明停止条件");
        }

        String stopEvidence = trimToNull(input.stopEvidence());
        String recoveryEvidence = trimToNull(input.recoveryEvidence());
        List<String> gaps = new ArrayList<>();
        boolean backupVerified = true;
        if (input.backupDrillId() != null) {
            backupVerified = backupDrillVerified(userId, input.backupDrillId());
            if (!backupVerified) gaps.add("BACKUP_DRILL_NOT_VERIFIED");
        }
        if (input.stopTriggered() && stopEvidence == null) gaps.add("STOP_EVIDENCE_MISSING");
        // 已验证的备份演练本身就是恢复证据；没有备份演练引用时才要求填写恢复证据。
        boolean recoveryCovered = recoveryEvidence != null
                || (input.backupDrillId() != null && backupVerified);
        if (!recoveryCovered) gaps.add("RECOVERY_EVIDENCE_MISSING");

        String result;
        if (!gaps.isEmpty()) {
            result = input.stopTriggered() && stopEvidence == null ? "FAILED" : "UNVERIFIED";
        } else {
            result = "VERIFIED";
        }

        jdbc.update("""
                INSERT INTO platform_experiment_drill
                  (user_id,evaluation_id,mode,scope,started_at,finished_at,stop_conditions,
                   stop_triggered,stop_evidence,recovery_evidence,backup_drill_id,result,gaps_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, userId, evaluationId, mode, scope, Timestamp.from(startedAt), Timestamp.from(finishedAt),
                writeList(stopConditions), input.stopTriggered() ? 1 : 0, stopEvidence, recoveryEvidence,
                input.backupDrillId(), result, writeList(gaps));
        long id = jdbc.query("""
                SELECT id FROM platform_experiment_drill WHERE user_id=? AND evaluation_id=?
                ORDER BY id DESC LIMIT 1
                """, rs -> rs.next() ? rs.getLong(1) : 0L, userId, evaluationId);
        return drillView(requireDrill(userId, id));
    }

    /* ── 卸载留证 ─────────────────────────────────────────────────────── */

    /** 记录卸载步骤已执行：没有证据不接受，避免"写了卸载步骤"就当作可退出。 */
    public EvaluationView recordExit(long userId, long evaluationId, String evidence) {
        requireEvaluation(userId, evaluationId);
        String text = requireText(evidence, "EXPERIMENT_EXIT_EVIDENCE_REQUIRED: 缺少卸载执行证据");
        jdbc.update("""
                UPDATE platform_experiment_evaluation SET exit_verified_at=?,exit_evidence=?,updated_at=?
                WHERE user_id=? AND id=?
                """, Timestamp.from(Instant.now()), text, Timestamp.from(Instant.now()), userId, evaluationId);
        return view(userId, requireEvaluation(userId, evaluationId));
    }

    /* ── 引入门槛 ─────────────────────────────────────────────────────── */

    private EvaluationView view(long userId, EvaluationRow row) {
        List<DrillRow> drills = jdbc.query("""
                SELECT * FROM platform_experiment_drill WHERE user_id=? AND evaluation_id=? ORDER BY id DESC
                """, DRILL_MAPPER, userId, row.id());
        int verified = (int) drills.stream().filter(drill -> "VERIFIED".equals(drill.result())).count();
        boolean canAdopt = verified > 0 && row.exitVerifiedAt() != null;
        return new EvaluationView(row.id(), row.component(), row.title(), row.necessity(),
                row.businessTrigger(), row.controlPlane(), row.permissions(), row.compatibility(),
                row.costNote(), row.uninstallSteps(), row.exitVerifiedAt(), row.exitEvidence(),
                drills.size(), verified, canAdopt, row.createdAt());
    }

    private boolean backupDrillVerified(long userId, long backupDrillId) {
        List<String> results = jdbc.query("""
                SELECT d.result FROM backup_drill_record d
                JOIN backup_recovery_set s ON s.id=d.set_id
                WHERE s.user_id=? AND d.id=?
                """, (rs, rowNum) -> rs.getString(1), userId, backupDrillId);
        return results.stream().anyMatch("VERIFIED"::equals);
    }

    private EvaluationRow requireEvaluation(long userId, long id) {
        List<EvaluationRow> rows = jdbc.query(
                "SELECT * FROM platform_experiment_evaluation WHERE user_id=? AND id=?",
                EVALUATION_MAPPER, userId, id);
        if (rows.isEmpty()) throw new BusinessException(404, "EXPERIMENT_EVALUATION_NOT_FOUND: 评估不存在");
        return rows.get(0);
    }

    private DrillRow requireDrill(long userId, long id) {
        List<DrillRow> rows = jdbc.query(
                "SELECT * FROM platform_experiment_drill WHERE user_id=? AND id=?",
                DRILL_MAPPER, userId, id);
        if (rows.isEmpty()) throw new BusinessException(404, "EXPERIMENT_DRILL_NOT_FOUND: 演练记录不存在");
        return rows.get(0);
    }

    private DrillView drillView(DrillRow row) {
        return new DrillView(row.id(), row.evaluationId(), row.mode(), row.scope(), row.startedAt(),
                row.finishedAt(), readList(row.stopConditions()), row.stopTriggered(), row.stopEvidence(),
                row.recoveryEvidence(), row.backupDrillId(), row.result(), readList(row.gaps()), row.createdAt());
    }

    private static String requireText(String value, String message) {
        if (value == null || value.isBlank()) throw new BusinessException(400, message);
        return value.trim();
    }

    private static Instant requireInstant(Instant value, String message) {
        if (value == null) throw new BusinessException(400, message);
        return value;
    }

    private static String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static List<String> normalizeList(List<String> values) {
        if (values == null) return List.of();
        List<String> normalized = new ArrayList<>();
        for (String value : values) {
            String text = trimToNull(value);
            if (text != null) normalized.add(text);
        }
        return List.copyOf(normalized);
    }

    private static String writeList(List<String> values) {
        try {
            return JSON.writeValueAsString(values);
        } catch (Exception malformed) {
            throw new IllegalStateException("列表序列化失败", malformed);
        }
    }

    private static List<String> readList(String value) {
        if (value == null || value.isBlank()) return List.of();
        try {
            return JSON.readValue(value, new TypeReference<List<String>>() {});
        } catch (Exception malformed) {
            return List.of();
        }
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        Timestamp value = rs.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }

    private static Long nullableLong(ResultSet rs, String column) throws SQLException {
        long value = rs.getLong(column);
        return rs.wasNull() ? null : value;
    }

    /* ── 行模型与视图 ─────────────────────────────────────────────────── */

    private record EvaluationRow(long id, String component, String title, String necessity,
                                 String businessTrigger, String controlPlane, String permissions,
                                 String compatibility, String costNote, String uninstallSteps,
                                 Instant exitVerifiedAt, String exitEvidence, Instant createdAt) {}

    private record DrillRow(long id, long evaluationId, String mode, String scope, Instant startedAt,
                            Instant finishedAt, String stopConditions, boolean stopTriggered,
                            String stopEvidence, String recoveryEvidence, Long backupDrillId,
                            String result, String gaps, Instant createdAt) {}

    private static final RowMapper<EvaluationRow> EVALUATION_MAPPER = (rs, rowNum) -> new EvaluationRow(
            rs.getLong("id"), rs.getString("component"), rs.getString("title"), rs.getString("necessity"),
            rs.getString("business_trigger"), rs.getString("control_plane"), rs.getString("permissions"),
            rs.getString("compatibility"), rs.getString("cost_note"), rs.getString("uninstall_steps"),
            instant(rs, "exit_verified_at"), rs.getString("exit_evidence"), instant(rs, "created_at"));

    private static final RowMapper<DrillRow> DRILL_MAPPER = (rs, rowNum) -> new DrillRow(
            rs.getLong("id"), rs.getLong("evaluation_id"), rs.getString("mode"), rs.getString("scope"),
            instant(rs, "started_at"), instant(rs, "finished_at"), rs.getString("stop_conditions"),
            rs.getInt("stop_triggered") != 0, rs.getString("stop_evidence"), rs.getString("recovery_evidence"),
            nullableLong(rs, "backup_drill_id"), rs.getString("result"), rs.getString("gaps_json"),
            instant(rs, "created_at"));

    public record EvaluationInput(String component, String title, String necessity, String businessTrigger,
                                  String controlPlane, String permissions, String compatibility,
                                  String costNote, String uninstallSteps) {}

    public record DrillInput(String mode, String scope, Instant startedAt, Instant finishedAt,
                             List<String> stopConditions, boolean stopTriggered, String stopEvidence,
                             String recoveryEvidence, Long backupDrillId) {}

    public record EvaluationView(long id, String component, String title, String necessity,
                                 String businessTrigger, String controlPlane, String permissions,
                                 String compatibility, String costNote, String uninstallSteps,
                                 Instant exitVerifiedAt, String exitEvidence, int drillCount,
                                 int verifiedDrillCount, boolean canAdopt, Instant createdAt) {}

    public record DrillView(long id, long evaluationId, String mode, String scope, Instant startedAt,
                            Instant finishedAt, List<String> stopConditions, boolean stopTriggered,
                            String stopEvidence, String recoveryEvidence, Long backupDrillId,
                            String result, List<String> gaps, Instant createdAt) {}
}
