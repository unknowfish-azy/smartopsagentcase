package com.smartops.diagnostics.database;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * 数据库真实诊断服务（OPS-07）。
 *
 * <p>流程：引擎解析 → 团队授权 → 凭据解析 → 只读连接 → 适配器采集 → 汇总 → 审计。
 * 任何失败都先落审计再抛错，审计表只存引擎、目标、状态与稳定错误码，
 * 不存凭据、不存未脱敏 SQL。</p>
 *
 * <p>采集不到不等于故障：{@code DATA_MISSING} 会汇总为 {@code INCOMPLETE}，
 * 只有真实 {@code FAILED} 才把整体结论置为失败。</p>
 */
@Service
public class DatabaseDiagnosisService {

    private static final Logger log = LoggerFactory.getLogger(DatabaseDiagnosisService.class);

    /** 单个检查的证据字节预算，防止一条超长 DIGEST 撑爆响应与审计。 */
    static final int EVIDENCE_MAX_BYTES = 8 * 1024;

    private final DatabaseCredentialResolver credentialResolver;
    private final TeamResourceAuthorizer authorizer;
    private final List<DatabaseDiagnosticAdapter> adapters;
    private final JdbcTemplate jdbc;
    private final DatabaseConnectionProvider connectionProvider;

    public DatabaseDiagnosisService(DatabaseCredentialResolver credentialResolver,
                                    TeamResourceAuthorizer authorizer,
                                    List<DatabaseDiagnosticAdapter> adapters,
                                    JdbcTemplate jdbc,
                                    DatabaseConnectionProvider connectionProvider) {
        this.credentialResolver = credentialResolver;
        this.authorizer = authorizer;
        this.adapters = adapters;
        this.jdbc = jdbc;
        this.connectionProvider = connectionProvider;
    }

    public DatabaseDiagnosisResult diagnose(SessionUser actor, DatabaseDiagnosisRequest request) {
        DatabaseEngine engine = DatabaseEngine.parse(request.engine());
        if (!engine.implemented()) {
            throw new BusinessException(400, "DATABASE_ENGINE_NOT_IMPLEMENTED: " + engine.name()
                    + " " + engine.unavailableReason());
        }
        // 越权请求在写审计之前就拒绝：不留下伪造的诊断记录。
        if (request.teamId() != null) {
            authorizer.requireMember(actor, request.teamId(), "view");
        }
        DatabaseDiagnosticAdapter adapter = adapters.stream()
                .filter(candidate -> candidate.engine() == engine)
                .findFirst()
                .orElseThrow(() -> new BusinessException(400, "DATABASE_ENGINE_NOT_IMPLEMENTED: " + engine.name()
                        + " 适配器未注册"));

        Instant startedAt = Instant.now();
        DatabaseCredentialResolver.DatabaseCredential credential;
        try {
            credential = credentialResolver.resolve(actor == null ? null : actor.id(), request.credentialRef());
        } catch (RuntimeException e) {
            String errorCode = stableErrorCode(e);
            audit(actor, request, engine, sourceOf(request.credentialRef()), "FAILED",
                    "凭据解析失败: " + errorCode, errorCode);
            throw new BusinessException(502, "DATABASE_DIAGNOSIS_FAILED: " + errorCode);
        }

        DatabaseQueryLimits limits = new DatabaseQueryLimits(request.maxRows(), request.timeoutSeconds(),
                EVIDENCE_MAX_BYTES);
        DatabaseTarget target = new DatabaseTarget(engine, request.host(), request.port(),
                request.database(), request.timeoutSeconds());
        List<DatabaseCheck> checks;
        try (Connection connection = connectionProvider.open(target, credential.username(), credential.password())) {
            connection.setReadOnly(true);
            enforceMysqlSessionReadOnly(connection, engine);
            checks = adapter.diagnose(connection, limits);
        } catch (SQLException e) {
            String summary = "数据库连接或只读会话设置失败: " + SqlSanitizer.sanitize(e.getMessage());
            audit(actor, request, engine, credential.source(), "FAILED", summary, "DATABASE_CONNECTION_FAILED");
            throw new BusinessException(502, "DATABASE_DIAGNOSIS_FAILED: " + brief(summary));
        } catch (BusinessException e) {
            String errorCode = stableErrorCode(e);
            audit(actor, request, engine, credential.source(), "FAILED", "诊断执行失败: " + errorCode, errorCode);
            throw new BusinessException(502, "DATABASE_DIAGNOSIS_FAILED: " + errorCode);
        }

        Instant endedAt = Instant.now();
        boolean dataMissing = checks.stream().anyMatch(check -> "DATA_MISSING".equals(check.status()));
        String overallStatus = overallStatus(checks);
        List<String> warnings = checks.stream()
                .filter(check -> "WARNING".equals(check.status()))
                .map(check -> check.name() + ": " + brief(check.evidence()))
                .toList();
        audit(actor, request, engine, credential.source(), "SUCCEEDED", checkSummary(checks), null);

        DatabaseScope scope = new DatabaseScope(engine.name(), request.host(), request.port(),
                request.database(), request.teamId());
        return new DatabaseDiagnosisResult(scope, startedAt.toString(), endedAt.toString(),
                Duration.between(startedAt, endedAt).toMillis(), checks, overallStatus, dataMissing, warnings);
    }

    /* ── 会话只读强化 ─────────────────────────────────────────────────── */

    private static void enforceMysqlSessionReadOnly(Connection connection, DatabaseEngine engine) throws SQLException {
        if (engine != DatabaseEngine.MYSQL) {
            return;
        }
        String product = connection.getMetaData().getDatabaseProductName();
        if (product == null || !product.toLowerCase(Locale.ROOT).contains("mysql")) {
            // H2 等测试库没有 MySQL 的事务只读语法；只在真实 MySQL 上执行。
            return;
        }
        try (Statement statement = connection.createStatement()) {
            statement.setQueryTimeout(5);
            statement.execute("SET SESSION TRANSACTION READ ONLY");
        }
    }

    /* ── 汇总与审计 ───────────────────────────────────────────────────── */

    private static String overallStatus(List<DatabaseCheck> checks) {
        if (checks.stream().anyMatch(check -> "FAILED".equals(check.status()))) {
            return "FAILED";
        }
        if (checks.stream().anyMatch(check -> "WARNING".equals(check.status()))) {
            return "WARNING";
        }
        if (checks.stream().anyMatch(check -> "DATA_MISSING".equals(check.status()))) {
            return "INCOMPLETE";
        }
        return "OK";
    }

    private static String checkSummary(List<DatabaseCheck> checks) {
        StringBuilder summary = new StringBuilder();
        for (DatabaseCheck check : checks) {
            if (summary.length() > 0) {
                summary.append(';');
            }
            summary.append(check.name()).append('=').append(check.status());
        }
        String text = summary.toString();
        return text.length() <= 1000 ? text : text.substring(0, 1000);
    }

    private void audit(SessionUser actor, DatabaseDiagnosisRequest request, DatabaseEngine engine,
                       String credentialSource, String status, String summary, String errorCode) {
        try {
            jdbc.update("""
                    INSERT INTO database_diagnosis_audit
                        (actor_id, team_id, engine, target_host, target_port, database_name,
                         credential_source, status, check_summary, error_code, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    actor == null ? null : actor.id(),
                    request.teamId(),
                    engine.name(),
                    request.host(),
                    request.port(),
                    request.database(),
                    credentialSource,
                    status,
                    summary == null ? null : truncate(summary, 1000),
                    errorCode,
                    Timestamp.valueOf(LocalDateTime.now()));
        } catch (RuntimeException e) {
            // 审计写失败不能掩盖真实的诊断结论，但也必须留下可检索的日志。
            log.warn("database diagnosis audit write failed: {}", e.getMessage());
        }
    }

    private static String sourceOf(String credentialRef) {
        if (credentialRef == null) {
            return "UNRESOLVED";
        }
        if (credentialRef.trim().startsWith("env:")) {
            return "ENV";
        }
        if (credentialRef.trim().startsWith("credential:")) {
            return "CREDENTIAL_STORE";
        }
        return "UNRESOLVED";
    }

    /** 从异常消息头部提取稳定错误码，例如 {@code DB_CREDENTIAL_UNAVAILABLE: ...}。 */
    private static String stableErrorCode(RuntimeException e) {
        String message = e.getMessage();
        if (message == null || message.isBlank()) {
            return "DATABASE_DIAGNOSIS_FAILED";
        }
        int colon = message.indexOf(':');
        String head = (colon > 0 ? message.substring(0, colon) : message)
                .trim().toUpperCase(Locale.ROOT).replace(' ', '_');
        return head.matches("[A-Z][A-Z0-9_]{2,63}") ? head : "DATABASE_DIAGNOSIS_FAILED";
    }

    private static String brief(String value) {
        if (value == null) {
            return "";
        }
        String text = value.replace('\n', ' ').replace('\r', ' ').trim();
        return text.length() <= 300 ? text : text.substring(0, 300) + "...";
    }

    private static String truncate(String value, int maxLength) {
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }

    /* ── 对外模型 ─────────────────────────────────────────────────────── */

    public record DatabaseScope(String engine, String host, int port, String database, Long teamId) {
    }

    public record DatabaseDiagnosisResult(DatabaseScope scope, String startedAt, String endedAt,
                                          long durationMs, List<DatabaseCheck> checks, String overallStatus,
                                          boolean dataMissing, List<String> warnings) {
    }
}
