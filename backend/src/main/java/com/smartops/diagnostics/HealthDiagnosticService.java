package com.smartops.diagnostics;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.smartops.assistant.MiniAssistantEngine;
import com.smartops.config.BusinessSchemaHealthIndicator;
import com.smartops.security.SessionUser;
import com.smartops.service.HarborCatalogService;
import com.smartops.service.ObservabilityService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Service
public class HealthDiagnosticService {
    private final JdbcTemplate jdbc;
    private final BusinessSchemaHealthIndicator schema;
    private final DiagnosticTargetPolicy targets;
    private final MiniAssistantEngine mini;
    private final ObservabilityService observability;
    private final HarborCatalogService harbor;

    public HealthDiagnosticService(JdbcTemplate jdbc, BusinessSchemaHealthIndicator schema, DiagnosticTargetPolicy targets,
            MiniAssistantEngine mini, ObservabilityService observability, HarborCatalogService harbor) {
        this.jdbc = jdbc;
        this.schema = schema;
        this.targets = targets;
        this.mini = mini;
        this.observability = observability;
        this.harbor = harbor;
    }

    public Summary summary(SessionUser user) {
        DiagnosticTargetPolicy.requireUser(user);
        var checks = new ArrayList<Check>();
        checks.add(new Check("session", "服务端会话", "HEALTHY", "user", "LOCAL_CHECK", Instant.now().toString(), 0,
                "当前请求已通过服务端会话和 CSRF 边界", "无需处理"));
        var miniStatus = mini.status();
        checks.add(new Check("mini", "智维 Mini", miniStatus.available() ? "HEALTHY" : "UNHEALTHY", "user", "ACTIVE_PROBE",
                Instant.now().toString(), 0, miniStatus.detail(), "检查本地 Mini 运行时"));
        boolean hasTargets = !targets.list(user).isEmpty();
        checks.add(new Check("authorized-targets", "授权诊断目标", hasTargets ? "HEALTHY" : "UNCONFIGURED", "user", "CONFIGURATION",
                Instant.now().toString(), 0, hasTargets ? "已配置授权目标，但尚未进行主动探测" : "没有可用的管理员授权目标", "在工具中心选择目标执行检查"));
        return new Summary("user", List.copyOf(checks));
    }

    public Summary adminSummary(SessionUser user) {
        if (!DiagnosticTargetPolicy.administrator(user) || user.mustChangePassword())
            throw new org.springframework.security.access.AccessDeniedException("管理员门户需要管理员权限且账号必须完成密码初始化");
        var checks = new ArrayList<Check>();
        long started = System.nanoTime();
        boolean databaseHealthy;
        try {
            jdbc.queryForObject("SELECT 1", Integer.class);
            databaseHealthy = true;
        } catch (RuntimeException ex) {
            databaseHealthy = false;
        }
        checks.add(new Check("database", "数据库连接", databaseHealthy ? "HEALTHY" : "UNHEALTHY", "admin", "ACTIVE_PROBE",
                Instant.now().toString(), elapsed(started), databaseHealthy ? "数据库连接检查通过" : "数据库连接检查失败；关键表未继续检查", "检查数据库服务、连接池和凭据"));
        if (databaseHealthy) {
            long tableStarted = System.nanoTime();
            try {
                List<String> missing = schema.missingTables();
                checks.add(new Check("schema", "关键业务表", missing.isEmpty() ? "HEALTHY" : "UNHEALTHY", "admin", "ACTIVE_PROBE",
                        Instant.now().toString(), elapsed(tableStarted), missing.isEmpty() ? "关键表访问检查通过" : "部分关键表不可访问：" + String.join("、", missing), "检查数据库迁移和表权限"));
            } catch (RuntimeException ex) {
                checks.add(new Check("schema", "关键业务表", "NOT_CHECKED", "admin", "ACTIVE_PROBE", null, elapsed(tableStarted), "关键表检查未完成，数据库元数据读取失败", "检查数据库迁移、表权限和连接状态"));
            }
        } else {
            checks.add(new Check("schema", "关键业务表", "NOT_CHECKED", "admin", "ACTIVE_PROBE", null, 0, "数据库连接失败，未检查关键表", "先恢复数据库连接"));
        }
        var miniStatus = mini.status();
        checks.add(new Check("mini", "智维 Mini", miniStatus.available() ? "HEALTHY" : "UNHEALTHY", "admin", "ACTIVE_PROBE", Instant.now().toString(), 0, miniStatus.detail(), "检查本地 Mini 运行时"));
        var sourceStatus = observability.sources();
        boolean observabilityConfigured = sourceStatus.stream().anyMatch(ObservabilityService.SourceStatus::configured);
        checks.add(new Check("observability", "观测数据源", observabilityConfigured ? "HEALTHY" : "UNCONFIGURED", "admin", "CONFIGURATION", Instant.now().toString(), 0,
                sourceStatus.stream().map(source -> source.id() + (source.configured() ? " 已配置" : " 未配置")).reduce((a, b) -> a + "；" + b).orElse("未配置"), "在观测数据源中完成配置"));
        var harborStatus = harbor.status();
        checks.add(new Check("harbor", "Harbor 镜像仓库", harborStatus.configured() ? "NOT_CHECKED" : "UNCONFIGURED", "admin", "CONFIGURATION", Instant.now().toString(), 0,
                harborStatus.configured() ? "已配置，尚未主动探测" : "未配置镜像仓库", "从 Harbor 工作台执行只读检查"));
        int targetCount = targets.count(user);
        checks.add(new Check("targets", "服务诊断目标", targetCount == 0 ? "UNCONFIGURED" : "HEALTHY", "admin", "CONFIGURATION", Instant.now().toString(), 0,
                targetCount == 0 ? "未配置授权目标" : "已配置管理员授权目标", "在配置文件中维护固定地址和授权用户"));
        var policy = new Policy(targetCount, DiagnosticProbeLimiter.PER_USER_LIMIT, DiagnosticProbeLimiter.GLOBAL_LIMIT,
                DiagnosticTransport.CONNECT_TIMEOUT_MS, DiagnosticTransport.READ_TIMEOUT_MS, DiagnosticTransport.MAX_BODY_BYTES,
                true, observabilityConfigured, harborStatus.configured());
        return new Summary("admin", List.copyOf(checks), policy);
    }

    private static long elapsed(long started) { return Math.max(0, (System.nanoTime() - started) / 1_000_000); }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record Summary(String scope, List<Check> checks, Policy policy) {
        public Summary(String scope, List<Check> checks) { this(scope, checks, null); }
    }

    public record Policy(int targetCount, int perUserConcurrency, int globalConcurrency, int connectTimeoutMs,
            int readTimeoutMs, int maxResponseBytes, boolean miniConfigured, boolean observabilityConfigured, boolean harborConfigured) {}

    public record Check(String id, String label, String status, String scope, String checkKind, String checkedAt, long durationMs, String summary, String nextAction) {}
}
