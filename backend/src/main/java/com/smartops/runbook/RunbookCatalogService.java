package com.smartops.runbook;

import com.fasterxml.jackson.core.type.TypeReference;
import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRiskPolicy;
import com.smartops.runbook.RunbookEnums.Environment;
import com.smartops.runbook.RunbookEnums.OnFailure;
import com.smartops.runbook.RunbookEnums.Phase;
import com.smartops.runbook.RunbookEnums.Risk;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

/**
 * Runbook 目录：定义、不可变版本与步骤。
 *
 * <p>版本一旦保存就不可修改：审批和执行都按具体 version_id 读取，
 * 因此"改一下再执行"不可能让执行内容偏离已批准的内容。</p>
 */
@Service
public class RunbookCatalogService {

    private static final Pattern PARAM_NAME = Pattern.compile("[A-Za-z0-9_\\u4e00-\\u9fa5]{1,64}");
    private static final int MAX_BODY = 20_000;

    private final JdbcTemplate jdbc;
    private final OperationRiskPolicy riskPolicy = new OperationRiskPolicy();

    public RunbookCatalogService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /* ── 定义 ─────────────────────────────────────────────────────────── */

    @Transactional
    public RunbookView create(Long userId, String name, String description, String environment,
                              String declaredRisk, Long ownerId) {
        requireUser(userId);
        String safeName = required(name, 128, "RUNBOOK_NAME_REQUIRED");
        Environment env = Environment.of(environment);
        Risk risk = Risk.of(declaredRisk);
        if (existsByName(userId, safeName)) throw new BusinessException(409, "RUNBOOK_NAME_ALREADY_EXISTS");
        KeyHolder keys = new GeneratedKeyHolder();
        try {
            jdbc.update(connection -> {
                PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO runbook(user_id,name,description,environment,owner_id,declared_risk,enabled) "
                                + "VALUES(?,?,?,?,?,?,1)", Statement.RETURN_GENERATED_KEYS);
                statement.setLong(1, userId);
                statement.setString(2, safeName);
                statement.setString(3, RunbookSupport.truncate(description, 500));
                statement.setString(4, env.name());
                if (ownerId == null) statement.setLong(5, userId); else statement.setLong(5, ownerId);
                statement.setString(6, risk.name());
                return statement;
            }, keys);
        } catch (DuplicateKeyException raced) {
            throw new BusinessException(409, "RUNBOOK_NAME_ALREADY_EXISTS");
        }
        return detail(userId, generatedId(keys));
    }

    @Transactional
    public RunbookView update(Long userId, long id, String name, String description, String environment,
                              String declaredRisk, Boolean enabled) {
        RunbookRow current = requireRunbook(userId, id);
        String safeName = name == null ? current.name() : required(name, 128, "RUNBOOK_NAME_REQUIRED");
        if (!safeName.equals(current.name()) && existsByName(userId, safeName)) {
            throw new BusinessException(409, "RUNBOOK_NAME_ALREADY_EXISTS");
        }
        jdbc.update("UPDATE runbook SET name=?,description=?,environment=?,declared_risk=?,enabled=? WHERE id=? AND user_id=?",
                safeName,
                description == null ? current.description() : RunbookSupport.truncate(description, 500),
                Environment.of(environment == null ? current.environment() : environment).name(),
                Risk.of(declaredRisk == null ? current.declaredRisk() : declaredRisk).name(),
                enabled == null ? current.enabled() : enabled,
                id, userId);
        return detail(userId, id);
    }

    @Transactional(readOnly = true)
    public RunbookView detail(Long userId, long id) {
        RunbookRow row = requireRunbook(userId, id);
        VersionView current = row.currentVersion() == null ? null : loadVersion(row.id(), row.currentVersion());
        return new RunbookView(row.id(), row.userId(), row.name(), row.description(), row.environment(),
                row.ownerId(), row.declaredRisk(), row.enabled(), row.currentVersion(),
                current == null ? null : current.riskLevel(), current, row.createdAt(), row.updatedAt());
    }

    @Transactional(readOnly = true)
    public List<RunbookView> list(Long userId) {
        requireUser(userId);
        return jdbc.query("""
                SELECT r.id,r.user_id,r.name,r.description,r.environment,r.owner_id,r.declared_risk,r.enabled,
                       r.current_version,r.created_at,r.updated_at,v.risk_level AS current_risk
                  FROM runbook r
                  LEFT JOIN runbook_version v ON v.runbook_id=r.id AND v.version=r.current_version
                 WHERE r.user_id=?
                   AND LEFT(r.name, 14) <> '__multi_exec__'
                 ORDER BY r.id DESC LIMIT 200
                """, (result, ignored) -> new RunbookView(result.getLong("id"), result.getLong("user_id"),
                result.getString("name"), result.getString("description"), result.getString("environment"),
                (Long) result.getObject("owner_id"), result.getString("declared_risk"), result.getBoolean("enabled"),
                (Integer) result.getObject("current_version"), result.getString("current_risk"), null,
                instant(result.getTimestamp("created_at")), instant(result.getTimestamp("updated_at"))), userId);
    }

    /* ── 版本 ─────────────────────────────────────────────────────────── */

    @Transactional
    public VersionView saveVersion(Long userId, long runbookId, VersionDraft draft) {
        RunbookRow runbook = requireRunbook(userId, runbookId);
        if (draft == null) throw new BusinessException(400, "RUNBOOK_VERSION_REQUIRED");

        List<ParameterSpec> parameters = validateParameters(draft.parameters());
        List<StepSpec> steps = validateSteps(draft.steps());
        if (steps.stream().noneMatch(step -> step.phase().equals(Phase.EXECUTE.name()))) {
            throw new BusinessException(400, "RUNBOOK_EXECUTE_STEP_REQUIRED");
        }

        int timeoutSec = bounded(draft.timeoutSec(), 300, 5, 86_400);
        int retryLimit = bounded(draft.retryLimit(), 0, 0, 3);
        int concurrencyLimit = bounded(draft.concurrencyLimit(), 1, 1, 10);
        int batchSize = bounded(draft.batchSize(), 10, 1, 100);
        int canarySize = bounded(draft.canarySize(), 0, 0, 100);
        Risk risk = computeRisk(runbook, steps);

        Integer latest = jdbc.queryForObject("SELECT COALESCE(MAX(version),0) FROM runbook_version WHERE runbook_id=?",
                Integer.class, runbookId);
        int version = (latest == null ? 0 : latest) + 1;

        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO runbook_version(runbook_id,version,note,risk_level,parameters_json,selector_json,"
                            + "timeout_sec,retry_limit,concurrency_limit,batch_size,canary_size,idempotency_rule,created_by) "
                            + "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, runbookId);
            statement.setInt(2, version);
            statement.setString(3, RunbookSupport.truncate(draft.note(), 500));
            statement.setString(4, risk.name());
            statement.setString(5, RunbookSupport.toJson(parameters));
            statement.setString(6, selectorJson(draft.defaultRuntimeIds(), draft.selectorNote()));
            statement.setInt(7, timeoutSec);
            statement.setInt(8, retryLimit);
            statement.setInt(9, concurrencyLimit);
            statement.setInt(10, batchSize);
            statement.setInt(11, canarySize);
            statement.setString(12, idempotencyRule(draft.idempotencyRule()));
            statement.setLong(13, userId);
            return statement;
        }, keys);
        long versionId = generatedId(keys);

        for (StepSpec step : steps) {
            jdbc.update("""
                    INSERT INTO runbook_step(version_id,phase,seq,name,body,expect_exit_code,on_failure,timeout_sec)
                    VALUES(?,?,?,?,?,?,?,?)
                    """, versionId, step.phase(), step.seq(), step.name(), step.body(),
                    step.expectExitCode(), step.onFailure(), step.timeoutSec());
        }
        return loadVersion(runbookId, version);
    }

    @Transactional
    public RunbookView publish(Long userId, long runbookId) {
        requireRunbook(userId, runbookId);
        Integer latest = jdbc.queryForObject("SELECT COALESCE(MAX(version),0) FROM runbook_version WHERE runbook_id=?",
                Integer.class, runbookId);
        if (latest == null || latest == 0) throw new BusinessException(409, "RUNBOOK_VERSION_REQUIRED");
        Integer executeSteps = jdbc.queryForObject("""
                SELECT COUNT(*) FROM runbook_step s JOIN runbook_version v ON v.id=s.version_id
                 WHERE v.runbook_id=? AND v.version=? AND s.phase='EXECUTE'
                """, Integer.class, runbookId, latest);
        if (executeSteps == null || executeSteps == 0) throw new BusinessException(409, "RUNBOOK_EXECUTE_STEP_REQUIRED");
        jdbc.update("UPDATE runbook SET current_version=? WHERE id=? AND user_id=?", latest, runbookId, userId);
        return detail(userId, runbookId);
    }

    @Transactional(readOnly = true)
    public List<VersionView> versions(Long userId, long runbookId) {
        requireRunbook(userId, runbookId);
        return jdbc.query("SELECT version FROM runbook_version WHERE runbook_id=? ORDER BY version DESC",
                (result, ignored) -> loadVersion(runbookId, result.getInt("version")), runbookId);
    }

    /** 供执行服务读取：返回不可变版本快照与步骤。 */
    VersionView loadVersion(long runbookId, int version) {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT id,runbook_id,version,note,risk_level,parameters_json,selector_json,timeout_sec,retry_limit,
                       concurrency_limit,batch_size,canary_size,idempotency_rule,created_at
                  FROM runbook_version WHERE runbook_id=? AND version=?
                """, runbookId, version);
        if (rows.isEmpty()) throw new BusinessException(404, "RUNBOOK_VERSION_NOT_FOUND");
        Map<String, Object> row = rows.get(0);
        long versionId = ((Number) row.get("id")).longValue();
        List<ParameterSpec> parameters = RunbookSupport.readList(
                (String) row.get("parameters_json"), new TypeReference<List<ParameterSpec>>() {});
        Map<String, Object> selector = readSelector((String) row.get("selector_json"));
        List<StepView> steps = jdbc.query("""
                SELECT id,phase,seq,name,body,expect_exit_code,on_failure,timeout_sec
                  FROM runbook_step WHERE version_id=?
                 ORDER BY CASE phase WHEN 'PRE_CHECK' THEN 0 WHEN 'EXECUTE' THEN 1
                                     WHEN 'POST_CHECK' THEN 2 ELSE 3 END, seq, id
                """, (result, ignored) -> new StepView(result.getLong("id"), result.getString("phase"),
                result.getInt("seq"), result.getString("name"), result.getString("body"),
                result.getInt("expect_exit_code"), result.getString("on_failure"),
                (Integer) result.getObject("timeout_sec")), versionId);
        @SuppressWarnings("unchecked")
        List<String> defaultTargets = (List<String>) selector.getOrDefault("runtimeIds", List.of());
        return new VersionView(versionId, runbookId, ((Number) row.get("version")).intValue(),
                (String) row.get("note"), (String) row.get("risk_level"), parameters, defaultTargets,
                (String) selector.get("note"), ((Number) row.get("timeout_sec")).intValue(),
                ((Number) row.get("retry_limit")).intValue(), ((Number) row.get("concurrency_limit")).intValue(),
                ((Number) row.get("batch_size")).intValue(), ((Number) row.get("canary_size")).intValue(),
                (String) row.get("idempotency_rule"), steps, instant((Timestamp) row.get("created_at")));
    }

    RunbookRow requireRunbook(Long userId, long id) {
        requireUser(userId);
        List<RunbookRow> rows = jdbc.query("""
                SELECT id,user_id,name,description,environment,owner_id,declared_risk,enabled,current_version,
                       created_at,updated_at
                  FROM runbook WHERE id=? AND user_id=?
                """, (result, ignored) -> new RunbookRow(result.getLong("id"), result.getLong("user_id"),
                result.getString("name"), result.getString("description"), result.getString("environment"),
                (Long) result.getObject("owner_id"), result.getString("declared_risk"), result.getBoolean("enabled"),
                (Integer) result.getObject("current_version"), instant(result.getTimestamp("created_at")),
                instant(result.getTimestamp("updated_at"))), id, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "RUNBOOK_NOT_FOUND");
        return rows.get(0);
    }

    /* ── 校验 ─────────────────────────────────────────────────────────── */

    private List<ParameterSpec> validateParameters(List<ParameterSpec> raw) {
        if (raw == null) return List.of();
        List<ParameterSpec> normalized = new ArrayList<>();
        Set<String> names = new HashSet<>();
        for (ParameterSpec item : raw) {
            if (item == null) throw new BusinessException(400, "RUNBOOK_PARAMETER_INVALID");
            String name = item.name() == null ? "" : item.name().trim();
            if (!PARAM_NAME.matcher(name).matches()) throw new BusinessException(400, "RUNBOOK_PARAMETER_NAME_INVALID");
            if (!names.add(name)) throw new BusinessException(400, "RUNBOOK_PARAMETER_DUPLICATED");
            String type = normalizeType(item.type());
            Pattern compiled = null;
            if (RunbookSupport.hasText(item.pattern())) {
                try {
                    compiled = Pattern.compile(item.pattern());
                } catch (PatternSyntaxException invalid) {
                    throw new BusinessException(400, "RUNBOOK_PARAMETER_PATTERN_INVALID");
                }
            }
            if (RunbookSupport.hasText(item.defaultValue())) {
                assertType(name, type, item.defaultValue(), compiled);
            }
            normalized.add(new ParameterSpec(name, type, item.required(), item.defaultValue(), item.pattern(),
                    RunbookSupport.truncate(item.description(), 200)));
        }
        return normalized;
    }

    private static String normalizeType(String type) {
        String text = type == null ? "STRING" : type.trim().toUpperCase(java.util.Locale.ROOT);
        if (!List.of("STRING", "NUMBER", "BOOLEAN").contains(text)) {
            throw new BusinessException(400, "RUNBOOK_PARAMETER_TYPE_INVALID");
        }
        return text;
    }

    /** 参数类型校验；这里与计划阶段共用同一口径，避免"保存能过、执行不能过"。 */
    static void assertType(String name, String type, String value, Pattern pattern) {
        if (value == null) return;
        switch (type) {
            case "NUMBER" -> {
                try {
                    new java.math.BigDecimal(value.trim());
                } catch (NumberFormatException invalid) {
                    throw new BusinessException(400, "RUNBOOK_PARAMETER_TYPE_MISMATCH:" + name);
                }
            }
            case "BOOLEAN" -> {
                String text = value.trim().toLowerCase(java.util.Locale.ROOT);
                if (!List.of("true", "false").contains(text)) {
                    throw new BusinessException(400, "RUNBOOK_PARAMETER_TYPE_MISMATCH:" + name);
                }
            }
            default -> { }
        }
        if (pattern != null && !pattern.matcher(value).matches()) {
            throw new BusinessException(400, "RUNBOOK_PARAMETER_PATTERN_MISMATCH:" + name);
        }
    }

    private List<StepSpec> validateSteps(List<StepSpec> raw) {
        if (raw == null || raw.isEmpty()) throw new BusinessException(400, "RUNBOOK_STEP_REQUIRED");
        List<StepSpec> normalized = new ArrayList<>();
        Set<String> keys = new HashSet<>();
        int fallbackSeq = 0;
        for (StepSpec item : raw) {
            if (item == null) throw new BusinessException(400, "RUNBOOK_STEP_INVALID");
            Phase phase = Phase.of(item.phase());
            int seq = item.seq() == null ? ++fallbackSeq : item.seq();
            if (seq <= 0) throw new BusinessException(400, "RUNBOOK_STEP_SEQ_INVALID");
            if (!keys.add(phase.name() + ":" + seq)) throw new BusinessException(400, "RUNBOOK_STEP_SEQ_DUPLICATED");
            String body = item.body() == null ? "" : item.body().trim();
            if (body.isEmpty()) throw new BusinessException(400, "RUNBOOK_STEP_BODY_REQUIRED");
            if (body.length() > MAX_BODY) throw new BusinessException(400, "RUNBOOK_STEP_BODY_TOO_LONG");
            int expectExit = item.expectExitCode() == null ? 0 : item.expectExitCode();
            if (expectExit < 0 || expectExit > 255) throw new BusinessException(400, "RUNBOOK_STEP_EXPECT_EXIT_INVALID");
            OnFailure onFailure = item.onFailure() == null
                    ? (phase == Phase.ROLLBACK ? OnFailure.CONTINUE : OnFailure.ABORT)
                    : OnFailure.of(item.onFailure());
            Integer stepTimeout = item.timeoutSec();
            if (stepTimeout != null && (stepTimeout < 1 || stepTimeout > 86_400)) {
                throw new BusinessException(400, "RUNBOOK_STEP_TIMEOUT_INVALID");
            }
            String name = RunbookSupport.hasText(item.name())
                    ? RunbookSupport.truncate(item.name(), 128)
                    : phase.name() + "-" + seq;
            normalized.add(new StepSpec(phase.name(), seq, name, body, expectExit, onFailure.name(), stepTimeout));
        }
        return normalized;
    }

    /** 版本风险 = 声明风险与各执行步骤实际内容的较高者。 */
    private Risk computeRisk(RunbookRow runbook, List<StepSpec> steps) {
        Risk risk = Risk.of(runbook.declaredRisk());
        boolean production = Environment.of(runbook.environment()).production();
        for (StepSpec step : steps) {
            if (!Phase.EXECUTE.name().equals(step.phase())) continue;
            var assessment = riskPolicy.assess(step.body(), false, production);
            risk = Risk.max(risk, Risk.of(assessment.risk().name()));
        }
        return risk;
    }

    private String selectorJson(List<String> runtimeIds, String note) {
        Map<String, Object> selector = new LinkedHashMap<>();
        List<String> targets = runtimeIds == null ? List.of() : runtimeIds.stream()
                .filter(RunbookSupport::hasText).map(String::trim).distinct().toList();
        selector.put("runtimeIds", targets);
        selector.put("note", RunbookSupport.truncate(note, 300));
        selector.put("resolution", "运行连接是会话级资源：计划时必须显式提供目标，服务端落库为目标快照");
        return RunbookSupport.toJson(selector);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> readSelector(String json) {
        if (json == null || json.isBlank()) return Map.of();
        try {
            Map<String, Object> parsed = new com.fasterxml.jackson.databind.ObjectMapper()
                    .readValue(json, new TypeReference<LinkedHashMap<String, Object>>() {});
            return parsed == null ? Map.of() : parsed;
        } catch (Exception malformed) {
            throw new IllegalStateException("RUNBOOK_JSON_MALFORMED", malformed);
        }
    }

    private static String idempotencyRule(String rule) {
        if (RunbookSupport.hasText(rule)) return RunbookSupport.truncate(rule, 500);
        return "同一运行内按 目标+attempt 幂等：已派发的 attempt 不会重复执行；"
                + "回滚步骤必须自身可重复执行，失败重试只增加 attempt，不覆盖既有证据。";
    }

    private static int bounded(Integer value, int fallback, int min, int max) {
        int raw = value == null ? fallback : value;
        if (raw < min || raw > max) throw new BusinessException(400, "RUNBOOK_LIMIT_OUT_OF_RANGE");
        return raw;
    }

    private static String required(String value, int max, String code) {
        if (!RunbookSupport.hasText(value)) throw new BusinessException(400, code);
        String text = value.trim();
        if (text.length() > max) throw new BusinessException(400, "RUNBOOK_TEXT_TOO_LONG");
        return text;
    }

    private static void requireUser(Long userId) {
        if (userId == null) throw new BusinessException(401, "RUNBOOK_USER_REQUIRED");
    }

    private boolean existsByName(Long userId, String name) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM runbook WHERE user_id=? AND name=?",
                Integer.class, userId, name);
        return count != null && count > 0;
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

    private static Instant instant(Timestamp value) { return value == null ? null : value.toInstant(); }

    /* ── 视图 ─────────────────────────────────────────────────────────── */

    public record ParameterSpec(String name, String type, boolean required, String defaultValue,
                                String pattern, String description) {}

    public record StepSpec(String phase, Integer seq, String name, String body, Integer expectExitCode,
                           String onFailure, Integer timeoutSec) {}

    public record VersionDraft(String note, List<ParameterSpec> parameters, List<String> defaultRuntimeIds,
                               String selectorNote, Integer timeoutSec, Integer retryLimit, Integer concurrencyLimit,
                               Integer batchSize, Integer canarySize, String idempotencyRule, List<StepSpec> steps) {}

    public record StepView(long id, String phase, int seq, String name, String body, int expectExitCode,
                           String onFailure, Integer timeoutSec) {}

    public record VersionView(long id, long runbookId, int version, String note, String riskLevel,
                              List<ParameterSpec> parameters, List<String> defaultRuntimeIds, String selectorNote,
                              int timeoutSec, int retryLimit, int concurrencyLimit, int batchSize, int canarySize,
                              String idempotencyRule, List<StepView> steps, Instant createdAt) {}

    public record RunbookView(long id, long userId, String name, String description, String environment,
                              Long ownerId, String declaredRisk, boolean enabled, Integer currentVersion,
                              String currentRisk, VersionView currentVersionDetail, Instant createdAt, Instant updatedAt) {}

    record RunbookRow(long id, long userId, String name, String description, String environment, Long ownerId,
                      String declaredRisk, boolean enabled, Integer currentVersion, Instant createdAt, Instant updatedAt) {}
}
