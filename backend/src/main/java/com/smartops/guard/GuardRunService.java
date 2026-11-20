package com.smartops.guard;

import com.smartops.dto.model.ModelConnectionResponse;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.exception.BusinessException;
import com.smartops.service.ModelConnectionService;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 智测盾测评执行与查询服务。
 *
 * <p>测评是异步的：创建任务后立即返回 runId，后台线程按用例顺序调用被测目标，
 * 逐条落库并更新进度。所有聚合分数都由 {@code guard_case_result} 重新计算，
 * 不缓存无法追溯的中间值。</p>
 */
@Service
public class GuardRunService {

    private static final Logger log = LoggerFactory.getLogger(GuardRunService.class);
    private static final int MAX_RESPONSE_CHARS = 4000;
    private static final int MAX_ERROR_CHARS = 300;

    private final JdbcTemplate jdbc;
    private final ModelConnectionService modelConnections;
    private final ExecutorService executor = Executors.newFixedThreadPool(2, runnable -> {
        Thread thread = new Thread(runnable, "agent-guard-runner");
        thread.setDaemon(true);
        return thread;
    });

    public GuardRunService(JdbcTemplate jdbc, ModelConnectionService modelConnections) {
        this.jdbc = jdbc;
        this.modelConnections = modelConnections;
    }

    @PreDestroy
    public void shutdown() {
        executor.shutdownNow();
    }

    public record CreateRunCommand(String targetType, String targetId, String suite, Boolean markBaseline) {
    }

    private record ResolvedTarget(String type, String id, String name) {
    }

    // ---------------------------------------------------------------- 目标

    public List<Map<String, Object>> targets(Long userId) {
        List<Map<String, Object>> rows = new ArrayList<>();
        rows.add(option("BUILTIN_STRICT", "builtin-strict", "内置智能体 · 严格策略",
                "确定性规则内核，不调用大模型，用于验证平台自身判定链路"));
        rows.add(option("BUILTIN_VULNERABLE", "builtin-vulnerable", "内置靶标 · 弱策略",
                "检测器自检靶标，故意暴露风险，不代表真实业务 Agent"));
        try {
            for (ModelConnectionResponse connection : modelConnections.list(userId)) {
                boolean enabled = Boolean.TRUE.equals(connection.getEnabled());
                rows.add(option("MODEL", String.valueOf(connection.getId()), connection.getName(),
                        "模型连接 · " + connection.getModelName() + (enabled ? " · 已启用" : " · 已禁用"),
                        enabled));
            }
        } catch (RuntimeException ex) {
            log.warn("读取模型连接失败，智测盾仅展示内置目标: {}", ex.getMessage());
        }
        return rows;
    }

    private Map<String, Object> option(String type, String id, String name, String subtitle) {
        return option(type, id, name, subtitle, true);
    }

    private Map<String, Object> option(String type, String id, String name, String subtitle, boolean available) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("type", type);
        row.put("id", id);
        row.put("name", name);
        row.put("subtitle", subtitle);
        row.put("available", available);
        return row;
    }

    private ResolvedTarget resolveTarget(Long userId, String rawType, String rawId) {
        String type = rawType == null ? "" : rawType.trim().toUpperCase(Locale.ROOT);
        if ("BUILTIN_STRICT".equals(type)) {
            return new ResolvedTarget(type, "builtin-strict", "内置智能体 · 严格策略");
        }
        if ("BUILTIN_VULNERABLE".equals(type)) {
            return new ResolvedTarget(type, "builtin-vulnerable", "内置靶标 · 弱策略（检测器自检）");
        }
        if ("MODEL".equals(type)) {
            long connectionId;
            try {
                connectionId = Long.parseLong(String.valueOf(rawId).trim());
            } catch (NumberFormatException ex) {
                throw new BusinessException(400, "模型连接 id 非法");
            }
            ModelConnectionResponse connection = modelConnections.list(userId).stream()
                    .filter(item -> connectionId == item.getId())
                    .findFirst()
                    .orElseThrow(() -> new BusinessException(404, "模型连接不存在"));
            if (!Boolean.TRUE.equals(connection.getEnabled())) {
                throw new BusinessException(409, "模型连接已禁用，无法作为测评目标");
            }
            return new ResolvedTarget(type, String.valueOf(connection.getId()),
                    connection.getName() + " · " + connection.getModelName());
        }
        throw new BusinessException(400, "不支持的被测目标类型");
    }

    // ---------------------------------------------------------------- 创建与执行

    public long createRun(Long userId, CreateRunCommand command) {
        if (command == null) {
            throw new BusinessException(400, "请求体不能为空");
        }
        ResolvedTarget target = resolveTarget(userId, command.targetType(), command.targetId());
        String suite = normalizeSuite(command.suite());
        List<GuardCase> cases = GuardCaseCatalog.forSuite(suite);
        if (cases.isEmpty()) {
            throw new BusinessException(400, "没有可执行的测评用例");
        }
        long runId = insertRun(userId, target, suite, cases.size());
        executor.submit(() -> executeRun(userId, runId, target, cases, Boolean.TRUE.equals(command.markBaseline())));
        return runId;
    }

    private void executeRun(Long userId, long runId, ResolvedTarget target, List<GuardCase> cases, boolean markBaseline) {
        try {
            jdbc.update("UPDATE guard_run SET status='RUNNING', started_at=? WHERE id=?",
                    now(), runId);
            for (GuardCase testCase : cases) {
                long started = System.nanoTime();
                String response = "";
                String error = null;
                GuardDetector.Outcome outcome;
                try {
                    response = respond(userId, target, testCase);
                    outcome = GuardDetector.inspect(testCase, response);
                    if (outcome.verdict() == GuardVerdict.ERROR) {
                        error = "被测目标返回空响应";
                    }
                } catch (RuntimeException ex) {
                    outcome = new GuardDetector.Outcome(GuardVerdict.ERROR, 0, List.of("TARGET_CALL_FAILED"));
                    error = safeError(ex);
                }
                long latencyMs = Math.max(0, (System.nanoTime() - started) / 1_000_000);
                insertResult(runId, testCase, response, outcome, latencyMs, error);
                bumpProgress(runId, outcome.verdict());
            }
            GuardScoring.Summary summary = summarizeRun(runId);
            // 基线标记与完成状态在同一条 UPDATE 中落库，避免前端轮询到 COMPLETED 时
            // 仍未看到 is_baseline=1 的短暂竞态。
            if (markBaseline) {
                jdbc.update("UPDATE guard_run SET is_baseline=0 WHERE user_id=? AND target_type=? AND target_id=?"
                        + " AND is_baseline=1 AND id<>?", userId, target.type(), target.id(), runId);
            }
            jdbc.update("UPDATE guard_run SET status='COMPLETED', score=?, risk_level=?, is_baseline=?, finished_at=?"
                            + " WHERE id=?",
                    summary.score(), summary.riskLevel(), markBaseline ? 1 : 0, now(), runId);
            applyRegression(userId, runId);
        } catch (RuntimeException ex) {
            log.warn("智测盾测评执行失败 runId={}: {}", runId, ex.getMessage());
            jdbc.update("UPDATE guard_run SET status='FAILED', error_message=?, finished_at=? WHERE id=?",
                    safeError(ex), now(), runId);
        }
    }

    private String respond(Long userId, ResolvedTarget target, GuardCase testCase) {
        if (target.type().startsWith("BUILTIN")) {
            return GuardBuiltinTarget.respond(target.type(), testCase);
        }
        ModelInvocationRequest request = new ModelInvocationRequest();
        request.setPrompt(testCase.prompt());
        request.setSystemPrompt(testCase.systemPrompt());
        request.setTemperature(0.0);
        // 安全测评只要判定所需的短回答；显式限制输出，避免网关按默认最大输出预留 TPM 配额导致 429。
        request.setMaxTokens(512);
        ModelInvocationResponse response = modelConnections.invoke(
                userId, Long.parseLong(target.id()), request);
        return response == null || response.getContent() == null ? "" : response.getContent();
    }

    private long insertRun(Long userId, ResolvedTarget target, String suite, int totalCases) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO guard_run(user_id,target_type,target_id,target_name,suite,status,total_cases,created_at)"
                            + " VALUES(?,?,?,?,?,?,?,?)",
                    Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, userId);
            ps.setString(2, target.type());
            ps.setString(3, target.id());
            ps.setString(4, truncate(target.name(), 128));
            ps.setString(5, suite);
            ps.setString(6, "QUEUED");
            ps.setInt(7, totalCases);
            ps.setTimestamp(8, now());
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        if (key == null) {
            throw new IllegalStateException("guard_run 主键生成失败");
        }
        return key.longValue();
    }

    private void insertResult(long runId, GuardCase testCase, String response,
                              GuardDetector.Outcome outcome, long latencyMs, String error) {
        jdbc.update("INSERT INTO guard_case_result(run_id,case_id,category,severity,title,prompt,response,"
                        + "verdict,risk_score,hit_rules,detector,owasp,latency_ms,error_message,created_at)"
                        + " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                runId,
                testCase.id(),
                testCase.category().name(),
                testCase.severity().name(),
                truncate(testCase.title(), 160),
                testCase.prompt(),
                truncate(response, MAX_RESPONSE_CHARS),
                outcome.verdict().name(),
                outcome.riskScore(),
                truncate(String.join(",", outcome.hitRules()), 500),
                testCase.detector().name(),
                testCase.category().owasp(),
                (int) Math.min(Integer.MAX_VALUE, latencyMs),
                truncate(error, MAX_ERROR_CHARS),
                now());
    }

    private void bumpProgress(long runId, GuardVerdict verdict) {
        switch (verdict) {
            case PASS -> jdbc.update("UPDATE guard_run SET passed_cases=passed_cases+1 WHERE id=?", runId);
            case FAIL -> jdbc.update("UPDATE guard_run SET failed_cases=failed_cases+1 WHERE id=?", runId);
            case ERROR -> jdbc.update("UPDATE guard_run SET error_cases=error_cases+1 WHERE id=?", runId);
        }
    }

    // ---------------------------------------------------------------- 查询

    public List<Map<String, Object>> listRuns(Long userId, int limit) {
        int capped = Math.max(1, Math.min(100, limit));
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT * FROM guard_run WHERE user_id=? ORDER BY id DESC LIMIT ?", userId, capped);
        List<Map<String, Object>> result = new ArrayList<>(rows.size());
        for (Map<String, Object> row : rows) {
            result.add(camelRun(row));
        }
        return result;
    }

    public Map<String, Object> runDetail(Long userId, long runId) {
        Map<String, Object> run = loadRun(userId, runId);
        List<Map<String, Object>> results = jdbc.queryForList(
                "SELECT case_id,category,severity,title,prompt,response,verdict,risk_score,hit_rules,"
                        + "detector,owasp,latency_ms,error_message FROM guard_case_result"
                        + " WHERE run_id=? ORDER BY id", runId);
        List<Map<String, Object>> camelResults = new ArrayList<>(results.size());
        for (Map<String, Object> row : results) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("caseId", text(row.get("case_id")));
            item.put("category", text(row.get("category")));
            item.put("categoryLabel", categoryLabel(text(row.get("category"))));
            item.put("severity", text(row.get("severity")));
            item.put("severityLabel", GuardSeverity.parse(text(row.get("severity"))).label());
            item.put("title", text(row.get("title")));
            item.put("prompt", text(row.get("prompt")));
            item.put("response", text(row.get("response")));
            item.put("verdict", text(row.get("verdict")));
            item.put("riskScore", number(row.get("risk_score")));
            item.put("hitRules", splitRules(text(row.get("hit_rules"))));
            item.put("detector", text(row.get("detector")));
            item.put("owasp", text(row.get("owasp")));
            item.put("latencyMs", number(row.get("latency_ms")));
            item.put("errorMessage", text(row.get("error_message")));
            camelResults.add(item);
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("run", camelRun(run));
        payload.put("results", camelResults);
        return payload;
    }

    public Map<String, Object> overview(Long userId) {
        List<Map<String, Object>> runs = jdbc.queryForList(
                "SELECT * FROM guard_run WHERE user_id=? ORDER BY id DESC LIMIT 8", userId);
        List<Map<String, Object>> camelRuns = new ArrayList<>(runs.size());
        for (Map<String, Object> row : runs) {
            camelRuns.add(camelRun(row));
        }

        Double average = jdbc.queryForObject(
                "SELECT AVG(score) FROM guard_run WHERE user_id=? AND status='COMPLETED' AND score IS NOT NULL",
                Double.class, userId);
        Integer totalRuns = jdbc.queryForObject(
                "SELECT COUNT(*) FROM guard_run WHERE user_id=?", Integer.class, userId);
        Integer blockedRuns = jdbc.queryForObject(
                "SELECT COUNT(*) FROM guard_run WHERE user_id=? AND regression_verdict='BLOCK'",
                Integer.class, userId);

        Long latestCompletedId = jdbc.query(
                "SELECT id FROM guard_run WHERE user_id=? AND status='COMPLETED' ORDER BY id DESC LIMIT 1",
                rs -> rs.next() ? rs.getLong("id") : null, userId);

        List<Map<String, Object>> categoryScores = new ArrayList<>();
        List<Map<String, Object>> riskFindings = new ArrayList<>();
        GuardScoring.Summary latestSummary = null;
        if (latestCompletedId != null) {
            latestSummary = summarizeRun(latestCompletedId);
            for (GuardScoring.CategoryScore category : latestSummary.categories()) {
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("category", category.category());
                row.put("label", category.label());
                row.put("score", category.score());
                row.put("total", category.total());
                row.put("failed", category.failed());
                row.put("error", category.error());
                categoryScores.add(row);
            }
            List<Map<String, Object>> findings = jdbc.queryForList(
                    "SELECT case_id,title,category,severity,risk_score FROM guard_case_result"
                            + " WHERE run_id=? AND verdict IN ('FAIL','ERROR')"
                            + " ORDER BY risk_score DESC, id ASC LIMIT 8", latestCompletedId);
            for (Map<String, Object> row : findings) {
                Map<String, Object> finding = new LinkedHashMap<>();
                finding.put("caseId", text(row.get("case_id")));
                finding.put("title", text(row.get("title")));
                finding.put("category", text(row.get("category")));
                finding.put("categoryLabel", categoryLabel(text(row.get("category"))));
                finding.put("severity", text(row.get("severity")));
                finding.put("severityLabel", GuardSeverity.parse(text(row.get("severity"))).label());
                finding.put("riskScore", number(row.get("risk_score")));
                riskFindings.add(finding);
            }
        }

        Map<String, Object> baseline = null;
        List<Map<String, Object>> baselineRows = jdbc.queryForList(
                "SELECT * FROM guard_run WHERE user_id=? AND is_baseline=1 ORDER BY id DESC LIMIT 1", userId);
        if (!baselineRows.isEmpty()) {
            baseline = camelRun(baselineRows.get(0));
        }

        List<Map<String, Object>> trend = new ArrayList<>();
        for (int index = camelRuns.size() - 1; index >= 0; index--) {
            Map<String, Object> run = camelRuns.get(index);
            if (!"COMPLETED".equals(run.get("status"))) {
                continue;
            }
            Map<String, Object> point = new LinkedHashMap<>();
            point.put("runId", run.get("id"));
            point.put("score", run.get("score"));
            point.put("riskLevel", run.get("riskLevel"));
            point.put("createdAt", run.get("createdAt"));
            point.put("targetName", run.get("targetName"));
            trend.add(point);
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("totalRuns", totalRuns == null ? 0 : totalRuns);
        payload.put("blockedRuns", blockedRuns == null ? 0 : blockedRuns);
        payload.put("averageScore", average == null ? null : Math.round(average * 10) / 10.0);
        payload.put("latestRun", camelRuns.isEmpty() ? null : camelRuns.get(0));
        payload.put("latestSummary", latestSummary == null ? null : latestSummary);
        payload.put("categoryScores", categoryScores);
        payload.put("riskFindings", riskFindings);
        payload.put("trend", trend);
        payload.put("baseline", baseline);
        return payload;
    }

    // ---------------------------------------------------------------- 基线与回归

    public Map<String, Object> markBaseline(Long userId, long runId) {
        Map<String, Object> row = loadRun(userId, runId);
        if (!"COMPLETED".equals(text(row.get("status")))) {
            throw new BusinessException(409, "只有已完成的测评才能设为基线");
        }
        jdbc.update("UPDATE guard_run SET is_baseline=0 WHERE user_id=? AND target_type=? AND target_id=? AND is_baseline=1",
                userId, text(row.get("target_type")), text(row.get("target_id")));
        jdbc.update("UPDATE guard_run SET is_baseline=1 WHERE id=?", runId);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("runId", runId);
        payload.put("baseline", true);
        return payload;
    }

    public Map<String, Object> regression(Long userId, long runId) {
        Map<String, Object> currentRow = loadRun(userId, runId);
        List<Map<String, Object>> baselineRows = jdbc.queryForList(
                "SELECT * FROM guard_run WHERE user_id=? AND target_type=? AND target_id=?"
                        + " AND is_baseline=1 AND id<>? ORDER BY id DESC LIMIT 1",
                userId, text(currentRow.get("target_type")), text(currentRow.get("target_id")), runId);
        Map<String, Object> payload = new LinkedHashMap<>();
        if (baselineRows.isEmpty()) {
            payload.put("available", false);
            payload.put("reason", number(currentRow.get("is_baseline")) == 1
                    ? "本次测评已是当前基线，后续同目标测评会自动与它比对。"
                    : "该目标尚未设置基线。请先在一次已完成测评上点击「设为基线」。");
            return payload;
        }
        Map<String, Object> baselineRow = baselineRows.get(0);
        long baselineId = ((Number) baselineRow.get("id")).longValue();
        int baselineScore = number(baselineRow.get("score"));
        int currentScore = number(currentRow.get("score"));

        List<GuardRegressionAnalyzer.ResultRow> baseline = loadResultRows(baselineId);
        List<GuardRegressionAnalyzer.ResultRow> current = loadResultRows(runId);
        GuardRegressionAnalyzer.Report report = GuardRegressionAnalyzer.compare(
                baselineScore, currentScore,
                GuardRegressionAnalyzer.index(baseline),
                GuardRegressionAnalyzer.index(current));

        jdbc.update("UPDATE guard_run SET baseline_run_id=?, regression_verdict=?, regression_summary=? WHERE id=?",
                baselineId, report.verdict(), truncate(report.summary(), 255), runId);

        payload.put("available", true);
        payload.put("baseline", camelRun(baselineRow));
        payload.put("current", camelRun(currentRow));
        payload.put("verdict", report.verdict());
        payload.put("summary", report.summary());
        payload.put("baselineScore", report.baselineScore());
        payload.put("currentScore", report.currentScore());
        payload.put("delta", report.delta());
        payload.put("newFailures", report.newFailures());
        payload.put("fixed", report.fixed());
        payload.put("persisting", report.persisting());
        return payload;
    }

    private void applyRegression(Long userId, long runId) {
        try {
            Map<String, Object> result = regression(userId, runId);
            if (!Boolean.TRUE.equals(result.get("available"))) {
                jdbc.update("UPDATE guard_run SET regression_verdict=NULL, regression_summary=NULL WHERE id=?", runId);
            }
        } catch (RuntimeException ex) {
            log.warn("智测盾回归比对失败 runId={}: {}", runId, ex.getMessage());
        }
    }

    public Map<String, Object> export(Long userId, long runId) {
        Map<String, Object> detail = runDetail(userId, runId);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("platform", "AgentGuard 智测盾");
        payload.put("exportedAt", LocalDateTime.now().toString());
        payload.put("run", detail.get("run"));
        payload.put("results", detail.get("results"));
        return payload;
    }

    // ---------------------------------------------------------------- 内部工具

    private GuardScoring.Summary summarizeRun(long runId) {
        List<GuardScoring.Item> items = new ArrayList<>();
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT category,severity,verdict FROM guard_case_result WHERE run_id=?", runId);
        for (Map<String, Object> row : rows) {
            items.add(new GuardScoring.Item(
                    category(text(row.get("category"))),
                    GuardSeverity.parse(text(row.get("severity"))),
                    GuardVerdict.parse(text(row.get("verdict")))));
        }
        return GuardScoring.summarize(items);
    }

    private List<GuardRegressionAnalyzer.ResultRow> loadResultRows(long runId) {
        List<GuardRegressionAnalyzer.ResultRow> rows = new ArrayList<>();
        for (Map<String, Object> row : jdbc.queryForList(
                "SELECT case_id,title,category,severity,verdict,risk_score FROM guard_case_result WHERE run_id=?",
                runId)) {
            rows.add(new GuardRegressionAnalyzer.ResultRow(
                    text(row.get("case_id")),
                    text(row.get("title")),
                    category(text(row.get("category"))),
                    GuardSeverity.parse(text(row.get("severity"))),
                    GuardVerdict.parse(text(row.get("verdict"))),
                    number(row.get("risk_score"))));
        }
        return rows;
    }

    private Map<String, Object> loadRun(Long userId, long runId) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT * FROM guard_run WHERE id=? AND user_id=?", runId, userId);
        if (rows.isEmpty()) {
            throw new BusinessException(404, "测评任务不存在");
        }
        return rows.get(0);
    }

    private Map<String, Object> camelRun(Map<String, Object> row) {
        Map<String, Object> run = new LinkedHashMap<>();
        run.put("id", number(row.get("id")));
        run.put("targetType", text(row.get("target_type")));
        run.put("targetId", text(row.get("target_id")));
        run.put("targetName", text(row.get("target_name")));
        run.put("suite", text(row.get("suite")));
        run.put("status", text(row.get("status")));
        run.put("score", row.get("score") == null ? null : number(row.get("score")));
        run.put("riskLevel", text(row.get("risk_level")));
        run.put("totalCases", number(row.get("total_cases")));
        run.put("passedCases", number(row.get("passed_cases")));
        run.put("failedCases", number(row.get("failed_cases")));
        run.put("errorCases", number(row.get("error_cases")));
        run.put("baseline", number(row.get("is_baseline")) == 1);
        run.put("baselineRunId", row.get("baseline_run_id") == null ? null : number(row.get("baseline_run_id")));
        run.put("regressionVerdict", text(row.get("regression_verdict")));
        run.put("regressionSummary", text(row.get("regression_summary")));
        run.put("errorMessage", text(row.get("error_message")));
        run.put("startedAt", timeText(row.get("started_at")));
        run.put("finishedAt", timeText(row.get("finished_at")));
        run.put("createdAt", timeText(row.get("created_at")));
        return run;
    }

    private String normalizeSuite(String raw) {
        if (raw == null || raw.isBlank()) {
            return "STANDARD";
        }
        String suite = raw.trim().toUpperCase(Locale.ROOT);
        return switch (suite) {
            case "SMOKE", "STANDARD", "FULL" -> suite;
            default -> "STANDARD";
        };
    }

    private GuardCategory category(String raw) {
        try {
            return GuardCategory.valueOf(raw);
        } catch (RuntimeException ex) {
            return GuardCategory.ROBUSTNESS;
        }
    }

    private String categoryLabel(String raw) {
        return category(raw).label();
    }

    private List<String> splitRules(String raw) {
        if (raw == null || raw.isBlank()) {
            return List.of();
        }
        List<String> rules = new ArrayList<>();
        for (String part : raw.split(",")) {
            if (!part.isBlank()) {
                rules.add(part.trim());
            }
        }
        return rules;
    }

    private String safeError(RuntimeException ex) {
        String message = ex.getMessage();
        if (message == null || message.isBlank()) {
            message = ex.getClass().getSimpleName();
        }
        return truncate(message, MAX_ERROR_CHARS);
    }

    private String text(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private int number(Object value) {
        if (value instanceof Number num) {
            return num.intValue();
        }
        // MySQL 驱动默认把 TINYINT(1) 映射为 Boolean，is_baseline 需要单独兼容。
        if (value instanceof Boolean flag) {
            return flag ? 1 : 0;
        }
        return 0;
    }

    private String timeText(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Timestamp timestamp) {
            return timestamp.toLocalDateTime().toString().replace('T', ' ');
        }
        if (value instanceof LocalDateTime dateTime) {
            return dateTime.toString().replace('T', ' ');
        }
        return String.valueOf(value);
    }

    private Timestamp now() {
        return Timestamp.valueOf(LocalDateTime.now());
    }

    private String truncate(String value, int max) {
        if (value == null || value.length() <= max) {
            return value;
        }
        return value.substring(0, max);
    }
}
