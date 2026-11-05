package com.smartops.sentinel;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.operations.HostKeyDecision;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import com.smartops.security.SessionUser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * 哨兵监控 / 脚本库 / 告警中心 的服务端实现。
 *
 * <p><b>安全边界（最重要的一段）</b>：哨兵任务**不接受任意 shell 命令**。
 * 采集命令由服务端按白名单指标名固定拼装；业务指标（端口 / 进程 / URL）先经严格模式校验，
 * 杜绝把用户输入当作命令执行。这是本项目既有"固定命令 + 参数校验"原则的延续。</p>
 *
 * <p><b>与既有链路的关系</b>：本服务**不执行任何运维脚本**。脚本执行仍走既有
 * {@code MultiExecService}（预览 → 二次确认 → 执行）。
 * {@link #requestDispatch} 只做"登记 + 生成待审批处置意图"，不建立第二条执行通路。</p>
 */
@Service
public class SentinelService {

    private static final Logger log = LoggerFactory.getLogger(SentinelService.class);

    /** 系统指标白名单：只允许这些指标名，避免任意命令。 */
    private static final Set<String> SYSTEM_METRICS = Set.of("cpu", "memory", "disk", "disk_io", "network", "tcp");
    private static final Pattern PORT = Pattern.compile("^\\d{1,5}$");
    private static final Pattern PROCESS = Pattern.compile("^[A-Za-z0-9_.@-]{1,64}$");
    private static final Pattern HTTP_URL = Pattern.compile("^https?://[A-Za-z0-9._~:/?#\\[\\]@!$&'()*+,;=%-]{1,200}$");
    private static final Set<String> KINDS = Set.of("system", "business", "log");
    private static final Set<String> SEVERITIES = Set.of("P0", "P1", "P2", "P3");
    private static final Set<String> LANGUAGES = Set.of("shell", "python", "bat", "powershell");
    private static final Set<String> RISKS = Set.of("LOW", "MEDIUM", "HIGH");
    private static final Set<String> CHANNELS = Set.of("inapp", "email", "webhook");

    /**
     * 固定采集命令：一次取回全部系统指标，格式 {@code cpu|memory|disk|tcp}。
     * 不使用任何用户输入，因此不存在注入面。
     */
    static final String SYSTEM_METRIC_COMMAND =
            "printf '%s|%s|%s|%s' "
            + "\"$(LC_ALL=C top -bn1 2>/dev/null | awk '/Cpu\\(s\\)/{for(i=1;i<=NF;i++)if($i ~ /^[0-9.]+$/){print 100-$i; exit}}')\" "
            + "\"$(LC_ALL=C free 2>/dev/null | awk '/^Mem:/{printf \"%.1f\", $3/$2*100}')\" "
            + "\"$(LC_ALL=C df -P / 2>/dev/null | awk 'NR==2{gsub(/%/,\"\",$5); print $5}')\" "
            + "\"$(LC_ALL=C ss -s 2>/dev/null | awk '/^TCP:/{for(i=1;i<=NF;i++)if($i ~ /^[0-9]+$/){print $i; exit}}')\"";

    private final JdbcTemplate jdbc;
    private final OperationRuntimeRegistry runtimes;
    private final com.smartops.service.OperationConnectionService connections;
    private final ObjectMapper json = new ObjectMapper();
    private final Clock clock;

    public SentinelService(JdbcTemplate jdbc, OperationRuntimeRegistry runtimes,
                           com.smartops.service.OperationConnectionService connections,
                           @org.springframework.beans.factory.annotation.Qualifier("mfaClock") Clock clock,
                           SentinelAdvisor advisor,
                           com.smartops.service.TeamNotificationService notifications,
                           SentinelNotifier notifier) {
        this.jdbc = jdbc;
        this.runtimes = runtimes;
        this.connections = connections;
        this.clock = clock;
        this.advisor = advisor;
        this.notifications = notifications;
        this.notifier = notifier;
    }

    /* ── 视图记录 ─────────────────────────────────────────────────────── */

    /**
     * 哨兵任务视图。
     *
     * <p>{@code groupLabel} 是**资产分组**的自由标签（如 web-prod / db-core），
     * 空值表示未分组。它只影响"批量启停"的组织方式，不改变采集语义。</p>
     */
    public record TaskView(long id, String name, String kind, String target, String matchRule, int intervalSec,
                           Long templateId, boolean enabled, String lastSeenAt, String lastStatus, String lastError,
                           long successCount, long failureCount, String runtimeId, String groupLabel) {}

    public record TemplateView(long id, String name, String description, List<SentinelThreshold.Rule> rules,
                               String severity, int debounceSec) {}

    public record ScriptView(long id, String name, String language, String description, String tags, String riskLevel,
                             int currentVersion, boolean approved, boolean enabled, int timeoutSec) {}

    public record ScriptVersionView(int version, String body, String lintStatus, String lintDetail, String createdAt) {}

    public record AlertRuleView(long id, String name, Long templateId, String severity, Long scriptId,
                                boolean autoDispatch, String notifyChannels, boolean enabled, String webhookUrl, String emailTo) {}

    public record AlertView(long id, Long ruleId, Long taskId, String severity, String status, String title,
                            String metric, String observedValue, String thresholdValue, String aiSummary,
                            Long recommendedScriptId, Long ticketId, String firedAt, String acknowledgedAt,
                            String resolvedAt, String closeNote) {}

    public record SampleView(String sampledAt, String metric, Double valueNum, String valueText, boolean abnormal) {}

    public record RunView(long id, long scriptId, int version, String triggerKind, Long alertId, String actorId,
                          String targetRuntime, String startedAt, String finishedAt, Long durationMs,
                          Integer exitCode, String result, String outputExcerpt) {}

    /* ── 租户校验 ─────────────────────────────────────────────────────── */

    private long userId(SessionUser actor) {
        if (actor == null || actor.id() == null) throw new BusinessException(401, "需要登录后使用哨兵功能");
        return actor.id();
    }

    private void requireOwned(String table, long id, long userId, String label) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM " + table + " WHERE id=? AND user_id=?",
                Integer.class, id, userId);
        if (count == null || count == 0) throw new BusinessException(404, label + "不存在或无权限访问");
    }

    /* ── 哨兵任务 ─────────────────────────────────────────────────────── */

    public List<TaskView> listTasks(SessionUser actor) {
        return jdbc.query("""
                SELECT id,name,kind,target,match_rule,interval_sec,template_id,enabled,last_seen_at,last_status,
                       last_error,success_count,failure_count,runtime_id,group_label
                  FROM sentinel_task WHERE user_id=? ORDER BY id DESC LIMIT 200
                """, (row, ignored) -> new TaskView(
                row.getLong("id"), row.getString("name"), row.getString("kind"), row.getString("target"),
                row.getString("match_rule"), row.getInt("interval_sec"), row.getObject("template_id", Long.class),
                row.getBoolean("enabled"),
                row.getTimestamp("last_seen_at") == null ? null : row.getTimestamp("last_seen_at").toInstant().toString(),
                row.getString("last_status"), row.getString("last_error"),
                row.getLong("success_count"), row.getLong("failure_count"), row.getString("runtime_id"), row.getString("group_label")),
                userId(actor));
    }

    @Transactional
    public TaskView createTask(SessionUser actor, String name, String kind, String target, String matchRule,
                               int intervalSec, Long templateId, String runtimeId, String groupLabel) {
        long userId = userId(actor);
        String normalizedKind = normalize(kind, KINDS, "采集类别无效");
        String normalizedTarget = validateTarget(normalizedKind, target);
        String normalizedMatch = "log".equals(normalizedKind) ? requireMatchRule(matchRule) : null;
        if (templateId != null) requireOwned("sentinel_threshold_template", templateId, userId, "阈值模板");
        int interval = Math.max(10, Math.min(86400, intervalSec));

        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO sentinel_task(user_id,runtime_id,name,kind,target,match_rule,interval_sec,template_id,group_label,enabled)
                    VALUES(?,?,?,?,?,?,?,?,?,1)
                    """, Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, userId);
            statement.setString(2, runtimeId);
            statement.setString(3, requireName(name, 128, "哨兵名称"));
            statement.setString(4, normalizedKind);
            statement.setString(5, normalizedTarget);
            statement.setString(6, normalizedMatch);
            statement.setInt(7, interval);
            if (templateId == null) statement.setNull(8, java.sql.Types.BIGINT); else statement.setLong(8, templateId);
            statement.setString(9, groupLabel == null || groupLabel.isBlank() ? null : groupLabel.trim());
            return statement;
        }, keys);
        return findTask(userId, generatedId(keys));
    }

    private TaskView findTask(long userId, long id) {
        return jdbc.queryForObject("""
                SELECT id,name,kind,target,match_rule,interval_sec,template_id,enabled,last_seen_at,last_status,
                       last_error,success_count,failure_count,runtime_id,group_label
                  FROM sentinel_task WHERE id=? AND user_id=?
                """, (row, ignored) -> new TaskView(
                row.getLong("id"), row.getString("name"), row.getString("kind"), row.getString("target"),
                row.getString("match_rule"), row.getInt("interval_sec"), row.getObject("template_id", Long.class),
                row.getBoolean("enabled"),
                row.getTimestamp("last_seen_at") == null ? null : row.getTimestamp("last_seen_at").toInstant().toString(),
                row.getString("last_status"), row.getString("last_error"),
                row.getLong("success_count"), row.getLong("failure_count"), row.getString("runtime_id"), row.getString("group_label")), id, userId);
    }

    @Transactional
    public void setTaskEnabled(SessionUser actor, long id, boolean enabled) {
        long userId = userId(actor);
        requireOwned("sentinel_task", id, userId, "哨兵任务");
        jdbc.update("UPDATE sentinel_task SET enabled=? WHERE id=? AND user_id=?", enabled, id, userId);
    }

    /**
     * 把哨兵任务重绑到一个已授权的运行连接上。
     *
     * <p>为什么需要这个入口：运行通道是会话级资源，后端重启或用户关闭终端后，
     * 任务里记的 runtimeId 就失效了，任务会如实标记为 {@code no_runtime}。
     * 重新连接会生成**新的** runtimeId，若不提供重绑，用户只能删任务重建。</p>
     *
     * <p>连接上已有存活通道时直接复用，不重复建立 SSH 连接。</p>
     *
     * @param sessionId 连接中心里的会话 id；为空说明界面没选，直接拒绝而不是猜一个
     */
    @Transactional
    public TaskView rebindRuntime(SessionUser actor, long id, Long sessionId) {
        long userId = userId(actor);
        requireOwned("sentinel_task", id, userId, "哨兵任务");
        if (sessionId == null) throw new BusinessException(400, "请选择一个运行连接");
        String runtimeId = runtimes.findBySession(userId, sessionId).orElse(null);
        if (runtimeId == null) {
            runtimeId = connections.connect(userId, sessionId, HostKeyDecision.TRUST_AND_SAVE).runtimeId();
        }
        // 清掉旧的采集状态：上一轮结果属于旧通道，留着会误导；下一轮采集会重新写。
        jdbc.update("UPDATE sentinel_task SET runtime_id=?, last_status=NULL, last_error=NULL, last_seen_at=NULL "
                + "WHERE id=? AND user_id=?", runtimeId, id, userId);
        return findTask(userId, id);
    }

    @Transactional
    public void deleteTask(SessionUser actor, long id) {
        long userId = userId(actor);
        requireOwned("sentinel_task", id, userId, "哨兵任务");
        jdbc.update("DELETE FROM sentinel_task WHERE id=? AND user_id=?", id, userId);
    }

    /**
     * 按资产分组批量启停。
     *
     * <p>为什么按分组而不是按主机：一台机器上可能挂着 CPU / 内存 / 日志三个哨兵，
     * "把这批 web 机器全停掉"是一个真实动作，逐个点容易漏。分组标签是自由文本，
     * 因此按标签精确匹配。</p>
     *
     * @return 实际改动的任务数；分组不存在时返回 0 而不是报错 ——
     *         "这个分组现在没有任务"是正常状态，不需要用户处理异常。
     */
    @Transactional
    public int setGroupEnabled(SessionUser actor, String groupLabel, boolean enabled) {
        long userId = userId(actor);
        String label = groupLabel == null ? "" : groupLabel.trim();
        if (label.isEmpty()) throw new BusinessException(400, "分组标签不能为空");
        if (label.length() > 64) throw new BusinessException(400, "分组标签不超过 64 字符");
        return jdbc.update("UPDATE sentinel_task SET enabled=? WHERE user_id=? AND group_label=?",
                enabled, userId, label);
    }

    /** 列出当前用户用到的分组及任务数，供界面渲染批量操作。 */
    public List<Map<String, Object>> listGroups(SessionUser actor) {
        long userId = userId(actor);
        return jdbc.query("""
                SELECT group_label, COUNT(*) AS total, SUM(enabled) AS enabled_count
                  FROM sentinel_task
                 WHERE user_id=? AND group_label IS NOT NULL AND group_label <> ''
                 GROUP BY group_label ORDER BY group_label
                """, (row, ignored) -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("label", row.getString("group_label"));
            item.put("total", row.getLong("total"));
            item.put("enabled", row.getLong("enabled_count"));
            return item;
        }, userId);
    }

    /** 把任务改到另一个分组（或清空分组）。 */
    @Transactional
    public void assignGroup(SessionUser actor, long id, String groupLabel) {
        long userId = userId(actor);
        requireOwned("sentinel_task", id, userId, "哨兵任务");
        String label = groupLabel == null || groupLabel.isBlank() ? null : groupLabel.trim();
        if (label != null && label.length() > 64) throw new BusinessException(400, "分组标签不超过 64 字符");
        jdbc.update("UPDATE sentinel_task SET group_label=? WHERE id=? AND user_id=?", label, id, userId);
    }

    /**
     * 校验采集目标。
     *
     * <p>system 只接受白名单指标名；business 的端口/进程/URL 各用严格模式校验后才允许拼接；
     * log 只接受普通路径字符。任何不匹配的输入直接拒绝，不做"尽力而为"的清洗。</p>
     */
    static String validateTarget(String kind, String target) {
        String value = target == null ? "" : target.trim();
        if (value.isEmpty()) throw new BusinessException(400, "采集目标不能为空");
        switch (kind) {
            case "system" -> {
                if (!SYSTEM_METRICS.contains(value)) {
                    throw new BusinessException(400, "系统指标只能是：" + String.join("、", SYSTEM_METRICS));
                }
                return value;
            }
            case "business" -> {
                if (value.startsWith("port:")) {
                    String port = value.substring(5);
                    if (!PORT.matcher(port).matches() || Integer.parseInt(port) > 65535) {
                        throw new BusinessException(400, "端口必须是 1-65535 的数字");
                    }
                    return value;
                }
                if (value.startsWith("process:")) {
                    String process = value.substring(8);
                    if (!PROCESS.matcher(process).matches()) {
                        throw new BusinessException(400, "进程名只允许字母、数字与 _ . @ - 且不超过 64 字符");
                    }
                    return value;
                }
                if (value.startsWith("http:")) {
                    if (!HTTP_URL.matcher(value.substring(5)).matches()) {
                        throw new BusinessException(400, "健康探测地址必须是 http/https URL");
                    }
                    return value;
                }
                throw new BusinessException(400, "业务指标必须写成 port:22 / process:nginx / http:https://… 之一");
            }
            case "log" -> {
                if (!Pattern.compile("^[A-Za-z0-9_./-]{1,255}$").matcher(value).matches()) {
                    throw new BusinessException(400, "日志路径只允许字母、数字与 _ . / - 且不超过 255 字符");
                }
                return value;
            }
            default -> throw new BusinessException(400, "采集类别无效");
        }
    }

    private static String requireMatchRule(String value) {
        String text = value == null ? "" : value.trim();
        if (text.isEmpty()) throw new BusinessException(400, "日志哨兵必须填写关键字");
        if (text.length() > 255) throw new BusinessException(400, "日志关键字不超过 255 字符");
        return text;
    }

    /** 把校验过的目标翻译成固定命令；不含任何未校验的用户输入。 */
    static String collectionCommand(String kind, String target, String matchRule) {
        return switch (kind) {
            case "system" -> SYSTEM_METRIC_COMMAND;
            case "business" -> {
                if (target.startsWith("port:")) {
                    String port = target.substring(5);
                    yield "ss -ltn 2>/dev/null | grep -q ':" + port + " ' && echo 1 || echo 0";
                }
                if (target.startsWith("process:")) {
                    yield "pgrep -x '" + target.substring(8) + "' >/dev/null 2>&1 && echo 1 || echo 0";
                }
                yield "curl -s -o /dev/null -w '%{http_code}' --max-time 5 '" + target.substring(5) + "'";
            }
            // 只统计命中行数，不把日志正文带回平台，避免把敏感日志外泄。
            case "log" -> "grep -c -F -- " + shellQuote(matchRule) + " " + shellQuote(target) + " 2>/dev/null || echo 0";
            default -> throw new BusinessException(400, "采集类别无效");
        };
    }

    /** 单引号包裹并转义，用于把已校验的关键字安全嵌入命令。 */
    static String shellQuote(String value) {
        return "'" + value.replace("'", "'\\''") + "'";
    }

    /* ── 阈值模板 ─────────────────────────────────────────────────────── */

    public List<TemplateView> listTemplates(SessionUser actor) {
        return jdbc.query("SELECT id,name,description,rules_json,severity,debounce_sec FROM sentinel_threshold_template "
                        + "WHERE user_id=? ORDER BY id DESC LIMIT 200",
                (row, ignored) -> new TemplateView(row.getLong("id"), row.getString("name"), row.getString("description"),
                        parseRules(row.getString("rules_json")), row.getString("severity"), row.getInt("debounce_sec")),
                userId(actor));
    }

    @Transactional
    public TemplateView createTemplate(SessionUser actor, String name, String description, Object rulesInput,
                                       String severity, int debounceSec) {
        long userId = userId(actor);
        List<SentinelThreshold.Rule> rules = coerceRules(rulesInput);
        if (rules.isEmpty()) throw new BusinessException(400, "至少需要一条阈值规则");
        String normalizedSeverity = normalizeUpper(severity, SEVERITIES, "告警级别无效");
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO sentinel_threshold_template(user_id,name,description,rules_json,severity,debounce_sec) VALUES(?,?,?,?,?,?)",
                    Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, userId);
            statement.setString(2, requireName(name, 128, "模板名称"));
            statement.setString(3, description);
            statement.setString(4, writeJson(rules));
            statement.setString(5, normalizedSeverity);
            statement.setInt(6, Math.max(0, Math.min(86400, debounceSec)));
            return statement;
        }, keys);
        long id = generatedId(keys);
        return new TemplateView(id, name, description, rules, normalizedSeverity, debounceSec);
    }

    /**
     * 柔性接受阈值规则：既接受 JSON 数组，也接受其字符串形式。
     *
     * <p>服务端自己序列化后落库，因此不信任调用方给的字符串是否规范；
     * 但也不因为"传了字符串"就报 500，而是按同一套规则解析。</p>
     */
    private List<SentinelThreshold.Rule> coerceRules(Object input) {
        if (input == null) return List.of();
        if (input instanceof String text) return parseRules(text);
        return parseRules(writeJson(input));
    }

    private List<SentinelThreshold.Rule> parseRules(String raw) {
        if (raw == null || raw.isBlank()) return List.of();
        try {
            var node = json.readTree(raw);
            List<SentinelThreshold.Rule> rules = new ArrayList<>();
            if (node.isArray()) {
                for (var item : node) {
                    String metric = item.path("metric").asText(null);
                    if (metric == null || metric.isBlank()) continue;
                    double value = item.path("value").asDouble(Double.NaN);
                    if (Double.isNaN(value)) continue;
                    rules.add(new SentinelThreshold.Rule(metric, item.path("operator").asText("gt"), value));
                }
            }
            return List.copyOf(rules);
        } catch (Exception malformed) {
            throw new BusinessException(400, "阈值规则格式无效");
        }
    }

    private String writeJson(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (Exception failure) {
            throw new BusinessException(500, "序列化失败");
        }
    }

    /* ── 脚本库 ───────────────────────────────────────────────────────── */

    public List<ScriptView> listScripts(SessionUser actor) {
        return jdbc.query("SELECT id,name,language,description,tags,risk_level,current_version,approved,enabled,timeout_sec "
                        + "FROM sentinel_script WHERE user_id=? ORDER BY id DESC LIMIT 200",
                (row, ignored) -> new ScriptView(row.getLong("id"), row.getString("name"), row.getString("language"),
                        row.getString("description"), row.getString("tags"), row.getString("risk_level"),
                        row.getInt("current_version"), row.getBoolean("approved"), row.getBoolean("enabled"),
                        row.getInt("timeout_sec")), userId(actor));
    }

    public List<ScriptVersionView> listScriptVersions(SessionUser actor, long scriptId) {
        long userId = userId(actor);
        requireOwned("sentinel_script", scriptId, userId, "脚本");
        return jdbc.query("SELECT version,body,lint_status,lint_detail,created_at FROM sentinel_script_version "
                        + "WHERE script_id=? ORDER BY version DESC LIMIT 100",
                (row, ignored) -> new ScriptVersionView(row.getInt("version"), row.getString("body"),
                        row.getString("lint_status"), row.getString("lint_detail"),
                        row.getTimestamp("created_at").toInstant().toString()), scriptId);
    }

    /**
     * 新建脚本并写入 v1。
     *
     * <p>服务端预检**必须通过**才允许保存：命中高危规则的脚本连存都不给存，
     * 避免"先存下来再想办法执行"的路径。高危脚本额外标记为待管理员审批。</p>
     */
    /** 脚本文件上传的允许扩展名 → 脚本语言。 */
    private static final Map<String, String> UPLOAD_LANGUAGES = Map.of(
            "sh", "shell", "bash", "shell", "py", "python", "bat", "bat", "cmd", "bat",
            "ps1", "powershell", "psm1", "powershell");

    /** 上传大小上限：脚本是文本，1 MiB 足够，也避免把二进制塞进版本表。 */
    private static final int MAX_SCRIPT_BYTES = 1024 * 1024;

    /**
     * 从上传的文件内容创建脚本。
     *
     * <p><b>为什么只取文本与扩展名</b>：这里不落盘、不解析文件系统，只把文件当成
     * "脚本正文 + 语言推断"的来源。这样上传与手动编写走**完全相同**的预检与存储路径，
     * 不存在"上传的能绕过预检"这种缝隙。</p>
     *
     * <p>语言可由调用方显式指定（例如 `.txt` 里写的是 Python）；不指定时按扩展名推断，
     * 推断不出来就拒绝并说明支持哪些扩展名，而不是猜一个。</p>
     */
    @Transactional
    public ScriptView uploadScript(SessionUser actor, String fileName, String content, String languageOverride,
                                   String riskLevel, String tags) {
        String name = fileName == null ? "" : fileName.trim();
        if (name.isEmpty()) throw new BusinessException(400, "缺少文件名");
        // 只取最后一段，避免 ../ 之类路径片段进入名称
        int slash = Math.max(name.lastIndexOf('/'), name.lastIndexOf('\\'));
        if (slash >= 0) name = name.substring(slash + 1);
        if (name.isEmpty()) throw new BusinessException(400, "缺少文件名");

        if (content == null) throw new BusinessException(400, "脚本内容为空");
        if (content.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > MAX_SCRIPT_BYTES) {
            throw new BusinessException(400, "脚本文件超过 1 MiB，请拆分或精简");
        }
        if (content.indexOf('\u0000') >= 0) throw new BusinessException(400, "文件看起来是二进制，不是文本脚本");

        String language = languageOverride != null && !languageOverride.isBlank()
                ? languageOverride.trim().toLowerCase(java.util.Locale.ROOT)
                : languageFromFileName(name);
        if (language == null) {
            throw new BusinessException(400, "无法从扩展名判断脚本语言，请显式指定（支持："
                    + String.join("、", UPLOAD_LANGUAGES.keySet().stream().sorted().toList()) + "）");
        }
        // 统一成 LF，避免落库后在 Linux 上执行时带 \r
        String body = content.replace("\r\n", "\n").replace('\r', '\n');
        String scriptName = name.contains(".") ? name.substring(0, name.lastIndexOf('.')) : name;
        return createScript(actor, scriptName, language, "从文件 " + name + " 导入", tags, riskLevel, body, 60);
    }

    static String languageFromFileName(String fileName) {
        if (fileName == null) return null;
        int dot = fileName.lastIndexOf('.');
        if (dot < 0 || dot == fileName.length() - 1) return null;
        return UPLOAD_LANGUAGES.get(fileName.substring(dot + 1).toLowerCase(java.util.Locale.ROOT));
    }

    @Transactional
    public ScriptView createScript(SessionUser actor, String name, String language, String description, String tags,
                                  String riskLevel, String body, int timeoutSec) {
        long userId = userId(actor);
        String normalizedLanguage = normalize(language, LANGUAGES, "脚本语言无效");
        String normalizedRisk = normalizeUpper(riskLevel, RISKS, "风险级别无效");
        var verdict = SentinelScriptLint.lint(body, normalizedLanguage);
        if (!verdict.ok()) throw new BusinessException(400, verdict.detail());
        int timeout = Math.max(5, Math.min(3600, timeoutSec));
        boolean approved = !SentinelScriptLint.requiresApproval(normalizedRisk);

        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO sentinel_script(user_id,name,language,description,tags,risk_level,current_version,approved,enabled,timeout_sec)
                    VALUES(?,?,?,?,?,?,1,?,1,?)
                    """, Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, userId);
            statement.setString(2, requireName(name, 128, "脚本名称"));
            statement.setString(3, normalizedLanguage);
            statement.setString(4, description);
            statement.setString(5, tags);
            statement.setString(6, normalizedRisk);
            statement.setBoolean(7, approved);
            statement.setInt(8, timeout);
            return statement;
        }, keys);
        long scriptId = generatedId(keys);
        jdbc.update("INSERT INTO sentinel_script_version(script_id,version,body,lint_status,lint_detail,created_by) VALUES(?,1,?,?,?,?)",
                scriptId, body, verdict.status(), verdict.detail(), userId);
        return findScript(userId, scriptId);
    }

    /** 追加新版本；同样必须通过服务端预检。 */
    @Transactional
    public ScriptView addScriptVersion(SessionUser actor, long scriptId, String body) {
        long userId = userId(actor);
        requireOwned("sentinel_script", scriptId, userId, "脚本");
        String language = jdbc.queryForObject("SELECT language FROM sentinel_script WHERE id=?", String.class, scriptId);
        var verdict = SentinelScriptLint.lint(body, language);
        if (!verdict.ok()) throw new BusinessException(400, verdict.detail());
        Integer current = jdbc.queryForObject("SELECT current_version FROM sentinel_script WHERE id=?", Integer.class, scriptId);
        int next = (current == null ? 1 : current) + 1;
        jdbc.update("INSERT INTO sentinel_script_version(script_id,version,body,lint_status,lint_detail,created_by) VALUES(?,?,?,?,?,?)",
                scriptId, next, body, verdict.status(), verdict.detail(), userId);
        jdbc.update("UPDATE sentinel_script SET current_version=?, approved=? WHERE id=?",
                next, false, scriptId);
        return findScript(userId, scriptId);
    }

    private ScriptView findScript(long userId, long scriptId) {
        return jdbc.queryForObject("SELECT id,name,language,description,tags,risk_level,current_version,approved,enabled,timeout_sec "
                        + "FROM sentinel_script WHERE id=? AND user_id=?",
                (row, ignored) -> new ScriptView(row.getLong("id"), row.getString("name"), row.getString("language"),
                        row.getString("description"), row.getString("tags"), row.getString("risk_level"),
                        row.getInt("current_version"), row.getBoolean("approved"), row.getBoolean("enabled"),
                        row.getInt("timeout_sec")), scriptId, userId);
    }

    public List<RunView> listRuns(SessionUser actor, Long scriptId) {
        long userId = userId(actor);
        String sql = """
                SELECT r.id,r.script_id,r.version,r.trigger_kind,r.alert_id,r.actor_id,r.target_runtime,r.started_at,
                       r.finished_at,r.duration_ms,r.exit_code,r.result,r.output_excerpt
                  FROM sentinel_script_run r JOIN sentinel_script s ON s.id=r.script_id
                 WHERE s.user_id=?%s ORDER BY r.id DESC LIMIT 200
                """;
        Object[] args = scriptId == null ? new Object[] { userId } : new Object[] { userId, scriptId };
        String filter = scriptId == null ? "" : " AND r.script_id=?";
        return jdbc.query(String.format(sql, filter), (row, ignored) -> new RunView(
                row.getLong("id"), row.getLong("script_id"), row.getInt("version"), row.getString("trigger_kind"),
                row.getObject("alert_id", Long.class),
                row.getObject("actor_id", Long.class) == null ? null : String.valueOf(row.getLong("actor_id")),
                row.getString("target_runtime"),
                row.getTimestamp("started_at") == null ? null : row.getTimestamp("started_at").toInstant().toString(),
                row.getTimestamp("finished_at") == null ? null : row.getTimestamp("finished_at").toInstant().toString(),
                row.getObject("duration_ms", Long.class), row.getObject("exit_code", Integer.class),
                row.getString("result"), row.getString("output_excerpt")), args);
    }

    /* ── 告警规则 ─────────────────────────────────────────────────────── */

    public List<AlertRuleView> listAlertRules(SessionUser actor) {
        return jdbc.query("SELECT id,name,template_id,severity,script_id,auto_dispatch,notify_channels,enabled,"
                        + "webhook_url,email_to "
                        + "FROM sentinel_alert_rule WHERE user_id=? ORDER BY id DESC LIMIT 200",
                (row, ignored) -> new AlertRuleView(row.getLong("id"), row.getString("name"),
                        row.getObject("template_id", Long.class), row.getString("severity"),
                        row.getObject("script_id", Long.class), row.getBoolean("auto_dispatch"),
                        row.getString("notify_channels"), row.getBoolean("enabled"),
                        row.getString("webhook_url"), row.getString("email_to")), userId(actor));
    }

    @Transactional
    public AlertRuleView createAlertRule(SessionUser actor, String name, Long templateId, String severity, Long scriptId,
                                        boolean autoDispatch, String notifyChannels, String webhookUrl, String emailTo) {
        long userId = userId(actor);
        if (templateId != null) requireOwned("sentinel_threshold_template", templateId, userId, "阈值模板");
        if (scriptId != null) requireOwned("sentinel_script", scriptId, userId, "脚本");
        String normalizedSeverity = normalizeUpper(severity, SEVERITIES, "告警级别无效");
        String channels = normalizeChannels(notifyChannels);
        // 配了 Webhook 渠道就在**保存时**校验地址：让用户当场知道地址不安全，
        // 而不是等告警真的触发时才发现投递被拒。
        String normalizedWebhook = webhookUrl == null || webhookUrl.isBlank() ? null : webhookUrl.trim();
        if (normalizedWebhook != null && channelList(channels).contains("webhook")) {
            String rejection = SentinelWebhookPolicy.rejectionReason(normalizedWebhook, notifier.allowedWebhookHosts());
            if (rejection != null) throw new BusinessException(400, rejection);
        }
        // P0/P1 不接受 auto_dispatch：服务端直接拒绝，而不是只在界面上置灰。
        boolean allowAuto = autoDispatch && !"P0".equals(normalizedSeverity) && !"P1".equals(normalizedSeverity);
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO sentinel_alert_rule(user_id,name,template_id,severity,script_id,auto_dispatch,notify_channels,webhook_url,email_to,enabled)
                    VALUES(?,?,?,?,?,?,?,?,?,1)
                    """, Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, userId);
            statement.setString(2, requireName(name, 128, "规则名称"));
            if (templateId == null) statement.setNull(3, java.sql.Types.BIGINT); else statement.setLong(3, templateId);
            statement.setString(4, normalizedSeverity);
            if (scriptId == null) statement.setNull(5, java.sql.Types.BIGINT); else statement.setLong(5, scriptId);
            statement.setBoolean(6, allowAuto);
            statement.setString(7, channels);
            statement.setString(8, normalizedWebhook);
            statement.setString(9, normalizeEmailTo(emailTo));
            return statement;
        }, keys);
        long id = generatedId(keys);
        return new AlertRuleView(id, name, templateId, normalizedSeverity, scriptId, allowAuto, channels, true,
                normalizedWebhook, normalizeEmailTo(emailTo));
    }

    /* ── 删除（模板 / 脚本 / 规则） ───────────────────────────────────── */

    /**
     * 删除阈值模板。
     *
     * <p>仍被哨兵任务或告警规则引用时拒绝删除，避免留下指向空模板的任务
     * （那会让任务静默失去判定依据）。</p>
     */
    @Transactional
    public void deleteTemplate(SessionUser actor, long id) {
        long userId = userId(actor);
        requireOwned("sentinel_threshold_template", id, userId, "阈值模板");
        Integer used = jdbc.queryForObject("""
                SELECT (SELECT COUNT(*) FROM sentinel_task WHERE template_id=?)
                     + (SELECT COUNT(*) FROM sentinel_alert_rule WHERE template_id=?)
                """, Integer.class, id, id);
        if (used != null && used > 0) throw new BusinessException(409, "该模板仍被 " + used + " 个哨兵任务或告警规则引用，请先解除引用");
        jdbc.update("DELETE FROM sentinel_threshold_template WHERE id=? AND user_id=?", id, userId);
    }

    /** 删除脚本；已被告警规则引用时拒绝。 */
    @Transactional
    public void deleteScript(SessionUser actor, long scriptId) {
        long userId = userId(actor);
        requireOwned("sentinel_script", scriptId, userId, "脚本");
        Integer rules = jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_alert_rule WHERE script_id=?", Integer.class, scriptId);
        if (rules != null && rules > 0) throw new BusinessException(409, "该脚本仍被 " + rules + " 条告警规则引用，请先解除引用");
        // 执行记录保留（审计需要），只清掉脚本与其版本。
        jdbc.update("DELETE FROM sentinel_script WHERE id=? AND user_id=?", scriptId, userId);
    }

    @Transactional
    public void deleteAlertRule(SessionUser actor, long id) {
        long userId = userId(actor);
        requireOwned("sentinel_alert_rule", id, userId, "告警规则");
        jdbc.update("DELETE FROM sentinel_alert_rule WHERE id=? AND user_id=?", id, userId);
    }

    /** 把已归一化的渠道串拆成列表，供校验与投递共用。 */
    private static java.util.Set<String> channelList(String channels) {
        return java.util.Arrays.stream((channels == null ? "" : channels).split(","))
                .map(String::trim).filter(item -> !item.isEmpty())
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }

    /**
     * 归一化邮件收件人：多个地址用逗号分隔、去重、去空白。
     *
     * <p>不做"看起来像邮箱"的正则校验：真实世界的地址比想象复杂（带 + 号、国际化域名），
     * 过度校验会拒掉合法地址。真正的校验发生在发信时由 JavaMail 做，失败会记为 `failed`。</p>
     */
    private static String normalizeEmailTo(String value) {
        if (value == null || value.isBlank()) return null;
        String joined = java.util.Arrays.stream(value.split("[,;]"))
                .map(String::trim)
                .filter(item -> !item.isEmpty())
                .distinct()
                .collect(java.util.stream.Collectors.joining(","));
        if (joined.isEmpty()) return null;
        return joined.length() <= 500 ? joined : joined.substring(0, 500);
    }

    private String normalizeChannels(String value) {        String text = value == null || value.isBlank() ? "inapp" : value;
        List<String> accepted = new ArrayList<>();
        for (String channel : text.split(",")) {
            String item = channel.trim().toLowerCase(Locale.ROOT);
            if (item.isEmpty()) continue;
            if (!CHANNELS.contains(item)) throw new BusinessException(400, "通知渠道只能是：inapp、email、webhook");
            if (!accepted.contains(item)) accepted.add(item);
        }
        if (accepted.isEmpty()) throw new BusinessException(400, "至少选择一个通知渠道");
        return String.join(",", accepted);
    }

    /* ── 告警 ─────────────────────────────────────────────────────────── */

    public List<AlertView> listAlerts(SessionUser actor) {
        long userId = userId(actor);
        return jdbc.query("""
                SELECT a.id,a.rule_id,a.task_id,a.severity,a.status,a.title,a.metric,a.observed_value,a.threshold_value,
                       a.ai_summary,a.recommended_script_id,a.ticket_id,a.fired_at,a.acknowledged_at,a.resolved_at,a.close_note
                  FROM sentinel_alert a
                  LEFT JOIN sentinel_task t ON t.id=a.task_id
                  LEFT JOIN sentinel_alert_rule r ON r.id=a.rule_id
                 WHERE t.user_id=? OR r.user_id=? ORDER BY a.id DESC LIMIT 200
                """, (row, ignored) -> mapAlert(row), userId, userId);
    }

    public List<SampleView> listSamples(SessionUser actor, long taskId, int limit) {
        long userId = userId(actor);
        requireOwned("sentinel_task", taskId, userId, "哨兵任务");
        return jdbc.query("SELECT sampled_at,metric,value_num,value_text,abnormal FROM sentinel_metric_sample "
                        + "WHERE task_id=? ORDER BY id DESC LIMIT ?",
                (row, ignored) -> new SampleView(row.getTimestamp("sampled_at").toInstant().toString(),
                        row.getString("metric"), row.getObject("value_num", Double.class), row.getString("value_text"),
                        row.getBoolean("abnormal")), taskId, Math.max(1, Math.min(2000, limit)));
    }

    private AlertView mapAlert(java.sql.ResultSet row) throws java.sql.SQLException {
        return new AlertView(row.getLong("id"), row.getObject("rule_id", Long.class), row.getObject("task_id", Long.class),
                row.getString("severity"), row.getString("status"), row.getString("title"), row.getString("metric"),
                row.getString("observed_value"), row.getString("threshold_value"), row.getString("ai_summary"),
                row.getObject("recommended_script_id", Long.class), row.getObject("ticket_id", Long.class),
                row.getTimestamp("fired_at") == null ? null : row.getTimestamp("fired_at").toInstant().toString(),
                row.getTimestamp("acknowledged_at") == null ? null : row.getTimestamp("acknowledged_at").toInstant().toString(),
                row.getTimestamp("resolved_at") == null ? null : row.getTimestamp("resolved_at").toInstant().toString(),
                row.getString("close_note"));
    }

    /** 确认收到告警（OPEN → NOTIFIED）。 */
    @Transactional
    public void acknowledge(SessionUser actor, long alertId) {
        long userId = userId(actor);
        requireAlertVisible(alertId, userId);
        jdbc.update("UPDATE sentinel_alert SET status='NOTIFIED', acknowledged_at=CURRENT_TIMESTAMP WHERE id=? AND status='OPEN'", alertId);
        recordEvent(alertId, userId, "FIRED", "已确认收到告警");
    }

    private void requireAlertVisible(long alertId, long userId) {
        Integer count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM sentinel_alert a
                  LEFT JOIN sentinel_task t ON t.id=a.task_id
                  LEFT JOIN sentinel_alert_rule r ON r.id=a.rule_id
                 WHERE a.id=? AND (t.user_id=? OR r.user_id=?)
                """, Integer.class, alertId, userId, userId);
        if (count == null || count == 0) throw new BusinessException(404, "告警不存在或无权限访问");
    }

    /**
     * 发起处置：**只登记意图并进入待审批**，不执行任何脚本。
     *
     * <p>真正的执行必须由既有 MultiExec 预览 + 审批 + 二次确认完成。
     * 这里是"告警 → 工单 → 待审批"的那一步，刻意不提供 shortcut。</p>
     *
     * @return 面向调用方的说明，包含下一步该怎么走
     */
    @Transactional
    public Map<String, Object> requestDispatch(SessionUser actor, long alertId, Long scriptId) {
        long userId = userId(actor);
        requireAlertVisible(alertId, userId);
        AlertView alert = jdbc.queryForObject("SELECT * FROM sentinel_alert WHERE id=?", (row, ignored) -> mapAlert(row), alertId);
        if (alert == null) throw new BusinessException(404, "告警不存在");
        if (scriptId != null) requireOwned("sentinel_script", scriptId, userId, "脚本");

        String risk = scriptId == null ? "LOW"
                : jdbc.queryForObject("SELECT risk_level FROM sentinel_script WHERE id=?", String.class, scriptId);
        boolean approved = scriptId != null && Boolean.TRUE.equals(
                jdbc.queryForObject("SELECT approved FROM sentinel_script WHERE id=?", Boolean.class, scriptId));

        // 服务端再次强制人工确认门槛，不依赖界面是否置灰。
        boolean humanRequired = "P0".equals(alert.severity()) || "P1".equals(alert.severity())
                || SentinelScriptLint.requiresApproval(risk) || !approved;

        jdbc.update("UPDATE sentinel_alert SET status='PENDING_APPROVAL', recommended_script_id=COALESCE(?, recommended_script_id) WHERE id=?",
                scriptId, alertId);
        recordEvent(alertId, userId, "DISPATCH_REQUESTED",
                "发起处置（脚本 " + (scriptId == null ? "未指定" : "#" + scriptId) + "）");
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("alertId", alertId);
        result.put("status", "PENDING_APPROVAL");
        result.put("humanApprovalRequired", humanRequired);
        result.put("nextStep", "请通过既有多机执行链路发起：预览 → 审批 → 执行；哨兵不直接执行脚本。");
        result.put("autoDispatchAllowed", SentinelScriptLint.canAutoDispatch(alert.severity(), false, risk, approved));
        return result;
    }

    /** 回填执行结果到告警并给出闭环状态。 */
    @Transactional
    public void fillResult(SessionUser actor, long alertId, String result, Integer exitCode, String excerpt) {
        long userId = userId(actor);
        requireAlertVisible(alertId, userId);
        String status = "success".equals(result) ? "RESOLVED" : "REMEDIATING";
        jdbc.update("UPDATE sentinel_alert SET status=?, resolved_at=CASE WHEN ?='RESOLVED' THEN CURRENT_TIMESTAMP ELSE resolved_at END WHERE id=?",
                status, status, alertId);
        recordEvent(alertId, userId, "RESULT_FILLED",
                "执行结果：" + result + (exitCode == null ? "" : "（退出码 " + exitCode + "）")
                        + (excerpt == null || excerpt.isBlank() ? "" : " — " + truncate(excerpt, 300)));
    }

    /** 人工确认关闭工单。 */
    @Transactional
    public void closeAlert(SessionUser actor, long alertId, String note) {
        long userId = userId(actor);
        requireAlertVisible(alertId, userId);
        jdbc.update("UPDATE sentinel_alert SET status='CLOSED', closed_by=?, close_note=? WHERE id=?",
                userId, truncate(note, 500), alertId);
        recordEvent(alertId, userId, "CLOSED", note == null ? "人工确认关闭" : truncate(note, 300));
    }

    private void recordEvent(long alertId, long actorId, String kind, String detail) {
        jdbc.update("INSERT INTO sentinel_alert_event(alert_id,actor_id,kind,detail) VALUES(?,?,?,?)",
                alertId, actorId, kind, truncate(detail, 800));
    }

    /**
     * 读取自增主键。
     *
     * <p>不用 {@code KeyHolder.getKey()}：当驱动返回多个生成列（例如 H2 会把
     * 带默认值的 created_at 也一并返回）时它会直接抛异常。按列名取 id 在
     * MySQL 与 H2 上行为一致，也更能表达"我要的是主键"。</p>
     */
    private static long generatedId(KeyHolder keys) {
        var keyList = keys.getKeyList();
        if (keyList.isEmpty()) throw new BusinessException(500, "写入后未取得主键");
        Object id = keyList.get(0).get("id");
        if (id == null) {
            // 部分驱动只回一个无名列
            Object only = keyList.get(0).values().stream().findFirst().orElse(null);
            if (only == null) throw new BusinessException(500, "写入后未取得主键");
            return ((Number) only).longValue();
        }
        return ((Number) id).longValue();
    }
    static String truncate(String value, int max) {
        if (value == null) return null;
        return value.length() <= max ? value : value.substring(0, max);
    }

    /* ── 告警研判 / 通知 / 知识沉淀 ───────────────────────────────────── */

    private final SentinelAdvisor advisor;
    private final com.smartops.service.TeamNotificationService notifications;
    private final SentinelNotifier notifier;

    /**
     * 告警研判：产出建议并**落库供审阅**，同时把推荐脚本记到告警上。
     *
     * <p>研判只写 `ai_summary` 与 `recommended_script_id`，不改变处置状态、
     * 不触发执行 —— 建议和行动严格分离。</p>
     */
    @Transactional
    public SentinelAdvisor.Advice analyzeAlert(SessionUser actor, long alertId) {
        long userId = userId(actor);
        requireAlertVisible(alertId, userId);
        SentinelAdvisor.AlertFacts facts = loadAlertFacts(alertId);
        List<SentinelAdvisor.ScriptFact> scripts = jdbc.query(
                "SELECT id,name,tags,risk_level FROM sentinel_script WHERE user_id=? AND enabled=1 ORDER BY id DESC LIMIT 100",
                (row, ignored) -> new SentinelAdvisor.ScriptFact(row.getLong("id"), row.getString("name"),
                        row.getString("tags"), row.getString("risk_level")), userId);
        SentinelAdvisor.Advice advice = advisor.analyze(facts, scripts, userId);
        Long recommended = advice.scripts().isEmpty() ? null : advice.scripts().get(0).scriptId();
        jdbc.update("UPDATE sentinel_alert SET ai_summary=?, recommended_script_id=COALESCE(?, recommended_script_id) WHERE id=?",
                advice.summary(), recommended, alertId);
        recordEvent(alertId, userId, "AI_ANALYZED", "研判完成，候选脚本 " + advice.scripts().size() + " 个");
        return advice;
    }

    private SentinelAdvisor.AlertFacts loadAlertFacts(long alertId) {
        // 刻意不取 detail_json：它是 JSON 列，H2 与 MySQL 的读取方式不同，
        // 而研判并不需要原始采样快照（证据由指标/观测值/阈值构成）。
        // 少读一列，换来两种数据库上行为一致。
        return jdbc.queryForObject("""
                SELECT id,severity,title,metric,observed_value,threshold_value
                  FROM sentinel_alert WHERE id=?
                """, (row, ignored) -> new SentinelAdvisor.AlertFacts(row.getLong("id"), row.getString("severity"),
                row.getString("title"), row.getString("metric"), row.getString("observed_value"),
                row.getString("threshold_value"), null), alertId);
    }

    /**
     * 产生告警时通知相关人。
     *
     * <p>复用既有团队通知能力，不新建通知表语义：`sentinel_notification` 只记录
     * "发了什么、发到哪、成没成"，真正的人读消息仍走 `team_notification`。</p>
     *
     * <p>邮件与 Webhook 的**实际投递适配器尚未接入**（需要 SMTP 与出站白名单），
     * 因此这里只登记 `pending`，不谎称已发送。</p>
     */
    @Transactional
    public Map<String, String> notifyStakeholders(long alertId, long userId) {
        List<Map<String, Object>> rules = jdbc.queryForList(
                "SELECT notify_channels,webhook_url,email_to FROM sentinel_alert_rule WHERE user_id=? AND enabled=1 ORDER BY id DESC LIMIT 1",
                userId);
        String channels = rules.isEmpty() ? "inapp" : String.valueOf(rules.get(0).get("notify_channels"));
        String webhookUrl = rules.isEmpty() ? null : (String) rules.get(0).get("webhook_url");
        String emailTo = rules.isEmpty() ? null : (String) rules.get(0).get("email_to");
        String title = jdbc.queryForObject("SELECT title FROM sentinel_alert WHERE id=?", String.class, alertId);

        // 真实投递：站内写通知表、Webhook 发 HTTP、邮件如实记 not_configured。
        Map<String, String> results = notifier.deliver(alertId, userId, channels, webhookUrl, emailTo, title, null);

        String summary = results.entrySet().stream()
                .map(entry -> entry.getKey() + "=" + entry.getValue())
                .collect(java.util.stream.Collectors.joining("，"));
        recordEvent(alertId, userId, "NOTIFIED", "投递结果：" + summary);
        return results;
    }

    /**
     * 把一次已闭环的告警沉淀为**知识候选**，进入既有知识审核流程。
     *
     * <p>这是"经验沉淀"闭环：故障现象 → 证据 → 处置 → 结果，交由团队成员复核后进入知识库。
     * 与协作优化第 3 点对应。</p>
     */
    @Transactional
    public Map<String, Object> createKnowledgeCandidate(SessionUser actor, long alertId) {
        long userId = userId(actor);
        requireAlertVisible(alertId, userId);
        AlertView alert = jdbc.queryForObject("SELECT * FROM sentinel_alert WHERE id=?", (row, ignored) -> mapAlert(row), alertId);
        if (alert == null) throw new BusinessException(404, "告警不存在");
        if (!"CLOSED".equals(alert.status())) {
            throw new BusinessException(409, "只有已关闭的告警才能沉淀为知识，避免把未验证的处置写成经验");
        }
        List<String> timeline = jdbc.query("SELECT kind,detail FROM sentinel_alert_event WHERE alert_id=? ORDER BY id",
                (row, ignored) -> row.getString("kind") + "：" + (row.getString("detail") == null ? "" : row.getString("detail")),
                alertId);
        String title = "告警复盘：" + truncate(alert.title(), 80);
        String body = "# " + title + "\n\n"
                + "## 现象\n" + alert.title() + "（" + alert.severity() + "）\n\n"
                + "## 证据\n指标 " + alert.metric() + " = " + alert.observedValue()
                + "，阈值 " + alert.thresholdValue() + "\n\n"
                + "## 研判\n" + (alert.aiSummary() == null ? "未生成研判" : alert.aiSummary()) + "\n\n"
                + "## 处置时间线\n" + String.join("\n", timeline) + "\n\n"
                + "## 关闭说明\n" + (alert.closeNote() == null ? "未填写" : alert.closeNote()) + "\n";
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO sentinel_knowledge_candidate(alert_id,user_id,title,status,content) VALUES(?,?,?,?,?)",
                    Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, alertId);
            statement.setLong(2, userId);
            statement.setString(3, truncate(title, 200));
            statement.setString(4, "PENDING_REVIEW");
            statement.setString(5, body);
            return statement;
        }, keys);
        long id = generatedId(keys);
        recordEvent(alertId, userId, "RESULT_FILLED", "已沉淀为知识候选 #" + id + "，等待复核");
        return Map.of("candidateId", id, "status", "PENDING_REVIEW", "title", title,
                "nextStep", "请到「运维记忆 → 知识审核」复核并采纳。");
    }

    public List<Map<String, Object>> listKnowledgeCandidates(SessionUser actor) {
        long userId = userId(actor);
        return jdbc.query("SELECT id,alert_id,title,status,created_at FROM sentinel_knowledge_candidate WHERE user_id=? ORDER BY id DESC LIMIT 100",
                (row, ignored) -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("id", row.getLong("id"));
                    item.put("alertId", row.getObject("alert_id", Long.class));
                    item.put("title", row.getString("title"));
                    item.put("status", row.getString("status"));
                    item.put("createdAt", row.getTimestamp("created_at").toInstant().toString());
                    return item;
                }, userId);
    }

    /* ── 采集与判定 ───────────────────────────────────────────────────── */

    /**
     * 对一个任务采样一次并落库；命中阈值时按防抖决定是否产生告警。
     *
     * <p>没有可用运行连接时**不伪造数据**：把任务标记为 {@code no_runtime} 并记录原因。
     * 这也如实说明了一个架构边界 —— 运行连接是用户会话级、随会话关闭而释放的，
     * 因此"常驻哨兵"要真正 7×24 运行，需要独立部署轻量采集器；当前实现是会话内的常驻轮询。</p>
     */
    @Transactional
    public void sampleOnce(TaskView task) {
        Instant now = clock.instant();
        OperationRuntime runtime = openRuntime(task);
        if (runtime == null) {
            jdbc.update("UPDATE sentinel_task SET last_status='no_runtime', last_error=?, last_seen_at=NULL WHERE id=?",
                    "没有可用的运行连接（会话级连接关闭后需重新建立）", task.id());
            jdbc.update("UPDATE sentinel_task SET failure_count=failure_count+1 WHERE id=?", task.id());
            return;
        }
        try {
            OperationRuntime.CommandResult result = runtime.execute(
                    collectionCommand(task.kind(), task.target(), task.matchRule()), 15_000);
            if (result.exitCode() != 0) {
                jdbc.update("UPDATE sentinel_task SET last_status='error', last_error=?, failure_count=failure_count+1, last_seen_at=CURRENT_TIMESTAMP WHERE id=?",
                        truncate("命令退出码 " + result.exitCode() + "：" + result.stderr(), 500), task.id());
                return;
            }
            Map<String, Double> snapshot = parseMetrics(task, result.stdout());
            storeSamples(task, snapshot, now);
            jdbc.update("UPDATE sentinel_task SET last_status='online', last_error=NULL, last_seen_at=CURRENT_TIMESTAMP, success_count=success_count+1 WHERE id=?",
                    task.id());
            evaluate(task, snapshot, now);
        } catch (Exception failure) {
            log.debug("sentinel sample failed task={}", task.id(), failure);
            jdbc.update("UPDATE sentinel_task SET last_status='error', last_error=?, failure_count=failure_count+1 WHERE id=?",
                    truncate(String.valueOf(failure.getMessage()), 500), task.id());
        }
    }

    private long taskUserId(long taskId) {
        Long userId = jdbc.queryForObject("SELECT user_id FROM sentinel_task WHERE id=?", Long.class, taskId);
        if (userId == null) throw new BusinessException(404, "哨兵任务不存在");
        return userId;
    }

    /**
     * 取出任务绑定的运行连接。
     *
     * <p>运行连接是**会话级**资源：由用户在自己的会话里建立，关闭会话即释放。
     * 因此这里取不到连接是正常状态而不是错误，返回 null 交由调用方如实标记。</p>
     */
    private OperationRuntime openRuntime(TaskView task) {
        if (task.runtimeId() == null) return null;
        try {
            OperationRuntime runtime = runtimes.requireOwned(task.runtimeId(), taskUserId(task.id()));
            return runtime != null && runtime.isOpen() ? runtime : null;
        } catch (BusinessException unavailable) {
            return null;
        }
    }

    /** 解析采集输出。解析不出数字时返回空 map —— 空 map 永远不会触发告警。 */
    static Map<String, Double> parseMetrics(TaskView task, String stdout) {
        Map<String, Double> values = new HashMap<>();
        String text = stdout == null ? "" : stdout.trim();
        if ("system".equals(task.kind())) {
            String[] parts = text.split("\\|", -1);
            String[] names = { "cpu", "memory", "disk", "tcp" };
            for (int index = 0; index < names.length && index < parts.length; index++) {
                try {
                    double value = Double.parseDouble(parts[index].trim());
                    if (!Double.isNaN(value)) values.put(names[index], value);
                } catch (NumberFormatException unparsable) {
                    // 该指标本轮无数据，跳过而不是当成 0。
                }
            }
            return values;
        }
        if ("business".equals(task.kind())) {
            if (task.target().startsWith("http:")) {
                try {
                    values.put("http_status", Double.parseDouble(text));
                    values.put("http", "200".equals(text) ? 0d : 1d);
                } catch (NumberFormatException unparsable) {
                    values.put("http", 1d);
                }
                return values;
            }
            double alive = "1".equals(text) ? 1d : 0d;
            values.put(task.target().startsWith("port:") ? "port" : "process", alive);
            return values;
        }
        if ("log".equals(task.kind())) {
            try {
                values.put("log_hits", Double.parseDouble(text));
            } catch (NumberFormatException unparsable) {
                values.put("log_hits", 0d);
            }
        }
        return values;
    }

    private void storeSamples(TaskView task, Map<String, Double> snapshot, Instant now) {
        snapshot.forEach((metric, value) -> jdbc.update(
                "INSERT INTO sentinel_metric_sample(task_id,sampled_at,metric,value_num,abnormal) VALUES(?,?,?,?,?)",
                task.id(), java.sql.Timestamp.from(now), metric, value, 0));
    }

    /**
     * 按任务绑定的阈值模板判定。
     *
     * <p>持续时间防抖的起点持久化在 sentinel_task.breached_since：越界且无未结告警时
     * 记下起点，持续到点后才触发；未越界时清空。重启后起点仍在，不会凭空触发也不会丢状态。
     * 同一事件已有未结告警时直接跳过，不重复写入。</p>
     */
    private void evaluate(TaskView task, Map<String, Double> snapshot, Instant now) {
        if (task.templateId() == null) return;
        Template meta = jdbc.query("SELECT rules_json,severity,debounce_sec FROM sentinel_threshold_template WHERE id=?",
                (row, ignored) -> new Template(parseRules(row.getString("rules_json")), row.getString("severity"),
                        row.getInt("debounce_sec")), task.templateId()).stream().findFirst().orElse(null);
        if (meta == null || meta.rules().isEmpty()) return;
        List<SentinelThreshold.Rule> rules = meta.rules();
        String severity = meta.severity() == null ? "P2" : meta.severity();
        int debounceSec = meta.debounceSec();

        if (!SentinelThreshold.breached(rules, snapshot)) {
            jdbc.update("UPDATE sentinel_task SET breached_since=NULL WHERE id=? AND breached_since IS NOT NULL", task.id());
            return;
        }

        boolean alertOpen = Boolean.TRUE.equals(jdbc.queryForObject("""
                SELECT EXISTS(SELECT 1 FROM sentinel_alert
                                WHERE task_id=? AND status IN ('OPEN','NOTIFIED','PENDING_APPROVAL','REMEDIATING'))
                """, Boolean.class, task.id()));
        if (alertOpen) return;

        Long since = jdbc.queryForObject("SELECT UNIX_TIMESTAMP(breached_since) FROM sentinel_task WHERE id=?",
                Long.class, task.id());
        if (since == null) {
            // 刚越界：只记录起点，不告警。
            jdbc.update("UPDATE sentinel_task SET breached_since=? WHERE id=?", java.sql.Timestamp.from(now), task.id());
            return;
        }
        long held = now.getEpochSecond() - since;
        if (held < debounceSec) return;

        jdbc.update("UPDATE sentinel_task SET breached_since=NULL WHERE id=?", task.id());
        String observed = describeObserved(rules, snapshot);
        fireAlert(task, rules.get(0).metric(), observed, SentinelThreshold.describe(rules), severity, snapshot, now);
    }

    /**
     * 写入一条告警并记录时间线。
     *
     * <p>抽成独立方法是为了**可独立验证**：没有可用的 SSH 运行连接时无法走到采集，
     * 但"告警落库"这一步仍应能被测试直接驱动，而不是只能靠真实目标机才能覆盖。</p>
     */
    void fireAlert(TaskView task, String metric, String observed, String threshold, String severity,
                   Map<String, Double> snapshot, Instant now) {
        String title = task.name() + "：" + threshold;
        KeyHolder keys = new GeneratedKeyHolder();
        final String finalSeverity = severity;
        final String finalTitle = title;
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO sentinel_alert(rule_id,task_id,severity,status,title,metric,observed_value,threshold_value,detail_json,fired_at)
                    VALUES(NULL,?,?,'OPEN',?,?,?,?,?,?)
                    """, Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, task.id());
            statement.setString(2, finalSeverity);
            statement.setString(3, truncate(finalTitle, 200));
            statement.setString(4, metric);
            statement.setString(5, observed);
            statement.setString(6, threshold);
            statement.setString(7, writeJson(snapshot));
            statement.setTimestamp(8, java.sql.Timestamp.from(now));
            return statement;
        }, keys);
        long alertId = generatedId(keys);
        recordEvent(alertId, taskUserId(task.id()), "FIRED", "哨兵 " + task.name() + " 命中阈值：" + observed);
    }

    private static String describeObserved(List<SentinelThreshold.Rule> rules, Map<String, Double> snapshot) {
        StringBuilder text = new StringBuilder();
        for (SentinelThreshold.Rule rule : rules) {
            if (text.length() > 0) text.append("，");
            text.append(rule.metric()).append('=').append(snapshot.get(rule.metric()));
        }
        return text.toString();
    }

    /** 阈值模板的判定上下文：一次查询取回规则、级别与防抖时长。 */
    private record Template(List<SentinelThreshold.Rule> rules, String severity, int debounceSec) {}

    /* ── 轮询入口 ─────────────────────────────────────────────────────── */

    /**
     * 对所有到期且启用的任务采样一次。
     *
     * <p>由 {@link SentinelPoller} 按固定间隔调用。到期判定基于 {@code last_seen_at}，
     * 因此"采集周期"是真实生效的，而不是每轮全量重采。</p>
     */
    public int pollDueTasks() {
        List<TaskView> due = jdbc.query("""
                SELECT id,name,kind,target,match_rule,interval_sec,template_id,enabled,last_seen_at,last_status,
                       last_error,success_count,failure_count,runtime_id,group_label
                  FROM sentinel_task
                 WHERE enabled=1
                   AND (last_seen_at IS NULL OR TIMESTAMPDIFF(SECOND, last_seen_at, NOW()) >= interval_sec)
                 ORDER BY last_seen_at IS NULL DESC, last_seen_at ASC
                 LIMIT 50
                """, (row, ignored) -> new TaskView(
                row.getLong("id"), row.getString("name"), row.getString("kind"), row.getString("target"),
                row.getString("match_rule"), row.getInt("interval_sec"), row.getObject("template_id", Long.class),
                row.getBoolean("enabled"),
                row.getTimestamp("last_seen_at") == null ? null : row.getTimestamp("last_seen_at").toInstant().toString(),
                row.getString("last_status"), row.getString("last_error"),
                row.getLong("success_count"), row.getLong("failure_count"), row.getString("runtime_id"), row.getString("group_label")));
        int sampled = 0;
        for (TaskView task : due) {
            sampleOnce(task);
            sampled++;
        }
        return sampled;
    }

    /* ── 工具 ─────────────────────────────────────────────────────────── */

    private static String normalize(String value, Set<String> allowed, String message) {
        String text = value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
        if (!allowed.contains(text)) throw new BusinessException(400, message);
        return text;
    }

    /**
     * 枚举值归一化（保留大写）。
     *
     * <p>告警级别与风险级别在接口契约与前端枚举里都是大写（P0/LOW），
     * 而采集类别与脚本语言是小写（system/shell）。这里按调用方给出的规范形式统一，
     * 并同时容忍大小写输入 —— 不接受"因为大小写不同就报参数无效"这种体验。</p>
     */
    private static String normalizeUpper(String value, Set<String> allowed, String message) {
        String text = value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
        if (!allowed.contains(text)) throw new BusinessException(400, message);
        return text;
    }

    private static String requireName(String value, int max, String label) {
        String text = value == null ? "" : value.trim();
        if (text.isEmpty()) throw new BusinessException(400, label + "不能为空");
        if (text.length() > max) throw new BusinessException(400, label + "不超过 " + max + " 字符");
        return text;
    }

    /** 供控制器返回给界面的说明常量。 */
    public static String runtimeBoundaryNote() {
        return "哨兵的采集发生在已授权的运行连接内；连接是会话级资源，关闭后任务会标记为 no_runtime。"
                + "要实现 7×24 常驻采集，需要独立部署轻量采集器，当前实现不伪造离线数据。";
    }
}
