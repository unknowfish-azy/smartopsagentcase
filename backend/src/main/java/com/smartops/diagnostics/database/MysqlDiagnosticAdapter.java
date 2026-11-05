package com.smartops.diagnostics.database;

import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * MySQL 只读诊断适配器（OPS-07）。
 *
 * <p>五项检查都走只读 SQL：连通性、会话只读语义、锁等待、慢 SQL、复制延迟。
 * 所有语句先过 {@link ReadOnlySqlGuard}，再按 {@link DatabaseQueryLimits} 设置
 * 查询超时与最大行数；证据按字节预算截断并标注 {@code [TRUNCATED]}。</p>
 *
 * <p>关键口径：{@code performance_schema} 表不存在（例如托管实例关闭了该库）时
 * 返回 {@code DATA_MISSING}，绝不报 {@code FAILED} —— 采集不到不是故障。</p>
 */
@Component
public class MysqlDiagnosticAdapter implements DatabaseDiagnosticAdapter {

    static final String CONNECTIVITY = "CONNECTIVITY";
    static final String READ_ONLY_SESSION = "READ_ONLY_SESSION";
    static final String LOCK_WAITS = "LOCK_WAITS";
    static final String SLOW_SQL = "SLOW_SQL";
    static final String REPLICATION_LAG = "REPLICATION_LAG";

    static final String STATUS_OK = "OK";
    static final String STATUS_WARNING = "WARNING";
    static final String STATUS_FAILED = "FAILED";
    static final String STATUS_DATA_MISSING = "DATA_MISSING";
    static final String STATUS_NOT_APPLICABLE = "NOT_APPLICABLE";

    /** 复制延迟告警阈值：60 秒。 */
    private static final long REPLICATION_LAG_WARNING_SECONDS = 60L;
    /** 慢 SQL 告警阈值：累计耗时超过 1 秒的摘要才值得人工介入。 */
    private static final double SLOW_SQL_WARNING_SECONDS = 1.0d;
    /** 锁等待证据最多展示 5 行，避免一次死锁风暴把证据撑爆。 */
    private static final int LOCK_WAIT_EVIDENCE_ROWS = 5;

    static final String LOCK_WAITS_SQL = """
            SELECT w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
                   w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
                   w.REQUESTING_ENGINE_LOCK_ID AS waiting_lock,
                   l.LOCK_TYPE AS lock_type,
                   l.LOCK_MODE AS lock_mode
            FROM performance_schema.data_lock_waits w
            LEFT JOIN performance_schema.data_locks l
                   ON l.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
            ORDER BY w.REQUESTING_ENGINE_TRANSACTION_ID""";

    static final String SLOW_SQL_SQL = "SELECT DIGEST_TEXT, COUNT_STAR, "
            + "ROUND(SUM_TIMER_WAIT/1000000000000,3) AS total_seconds "
            + "FROM performance_schema.events_statements_summary_by_digest "
            + "ORDER BY SUM_TIMER_WAIT DESC LIMIT ?";

    @Override
    public DatabaseEngine engine() {
        return DatabaseEngine.MYSQL;
    }

    @Override
    public List<DatabaseCheck> diagnose(Connection connection, DatabaseQueryLimits limits) {
        List<DatabaseCheck> checks = new ArrayList<>();
        checks.add(checkConnectivity(connection, limits));
        checks.add(checkReadOnlySession(connection, limits));
        checks.add(checkLockWaits(connection, limits));
        checks.add(checkSlowSql(connection, limits));
        checks.add(checkReplicationLag(connection, limits));
        return List.copyOf(checks);
    }

    private DatabaseCheck checkConnectivity(Connection connection, DatabaseQueryLimits limits) {
        String sql = "SELECT 1";
        Instant collectedAt = Instant.now();
        try (PreparedStatement statement = prepare(connection, sql, limits);
             ResultSet resultSet = statement.executeQuery()) {
            int rows = 0;
            while (resultSet.next()) {
                rows++;
            }
            return new DatabaseCheck(CONNECTIVITY, rows > 0 ? STATUS_OK : STATUS_DATA_MISSING,
                    sql, "只读连接可用，SELECT 1 返回 " + rows + " 行", rows, collectedAt.toString());
        } catch (SQLException e) {
            return new DatabaseCheck(CONNECTIVITY, STATUS_FAILED, sql,
                    bounded("连通性检查失败: " + brief(e), limits), 0, collectedAt.toString());
        }
    }

    private DatabaseCheck checkReadOnlySession(Connection connection, DatabaseQueryLimits limits) {
        String sql = "SELECT @@session.transaction_read_only";
        Instant collectedAt = Instant.now();
        try (PreparedStatement statement = prepare(connection, sql, limits);
             ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                return new DatabaseCheck(READ_ONLY_SESSION, STATUS_DATA_MISSING, sql,
                        bounded("未返回 transaction_read_only 变量值", limits), 0, collectedAt.toString());
            }
            int flag = resultSet.getInt(1);
            if (flag == 1) {
                return new DatabaseCheck(READ_ONLY_SESSION, STATUS_OK, sql,
                        "会话处于只读事务模式（transaction_read_only=1），诊断期间不可写",
                        1, collectedAt.toString());
            }
            return new DatabaseCheck(READ_ONLY_SESSION, STATUS_WARNING, sql,
                    "会话未强制只读（transaction_read_only=" + flag
                            + "）：连接由 JDBC setReadOnly 约束，但实例本身不是只读副本",
                    1, collectedAt.toString());
        } catch (SQLException e) {
            if (isMissingObject(e)) {
                return new DatabaseCheck(READ_ONLY_SESSION, STATUS_DATA_MISSING, sql,
                        bounded("会话只读变量不可读取: " + brief(e), limits), 0, collectedAt.toString());
            }
            return new DatabaseCheck(READ_ONLY_SESSION, STATUS_FAILED, sql,
                    bounded("会话只读变量读取失败: " + brief(e), limits), 0, collectedAt.toString());
        }
    }

    private DatabaseCheck checkLockWaits(Connection connection, DatabaseQueryLimits limits) {
        Instant collectedAt = Instant.now();
        try (PreparedStatement statement = prepare(connection, LOCK_WAITS_SQL, limits);
             ResultSet resultSet = statement.executeQuery()) {
            List<String> lines = new ArrayList<>();
            int rows = 0;
            while (resultSet.next()) {
                rows++;
                if (lines.size() < LOCK_WAIT_EVIDENCE_ROWS) {
                    lines.add("waiting_trx=" + resultSet.getString("waiting_trx")
                            + " blocking_trx=" + resultSet.getString("blocking_trx")
                            + " lock_type=" + resultSet.getString("lock_type")
                            + " lock_mode=" + resultSet.getString("lock_mode"));
                }
            }
            if (rows == 0) {
                return new DatabaseCheck(LOCK_WAITS, STATUS_OK, LOCK_WAITS_SQL,
                        "未发现锁等待（data_lock_waits 为空）", 0, collectedAt.toString());
            }
            return new DatabaseCheck(LOCK_WAITS, STATUS_WARNING, LOCK_WAITS_SQL,
                    bounded("发现 " + rows + " 条锁等待；前 " + lines.size() + " 行: "
                            + String.join(" | ", lines), limits), rows, collectedAt.toString());
        } catch (SQLException e) {
            if (isMissingObject(e)) {
                return new DatabaseCheck(LOCK_WAITS, STATUS_DATA_MISSING, LOCK_WAITS_SQL,
                        bounded("performance_schema.data_lock_waits 不可用（实例未开启或版本不支持）: "
                                + brief(e), limits), 0, collectedAt.toString());
            }
            return new DatabaseCheck(LOCK_WAITS, STATUS_FAILED, LOCK_WAITS_SQL,
                    bounded("锁等待查询失败: " + brief(e), limits), 0, collectedAt.toString());
        }
    }

    private DatabaseCheck checkSlowSql(Connection connection, DatabaseQueryLimits limits) {
        Instant collectedAt = Instant.now();
        try (PreparedStatement statement = prepare(connection, SLOW_SQL_SQL, limits)) {
            statement.setInt(1, Math.max(1, limits.maxRows()));
            try (ResultSet resultSet = statement.executeQuery()) {
                List<String> lines = new ArrayList<>();
                int rows = 0;
                boolean overThreshold = false;
                while (resultSet.next()) {
                    rows++;
                    double totalSeconds = resultSet.getDouble("total_seconds");
                    if (totalSeconds >= SLOW_SQL_WARNING_SECONDS) {
                        overThreshold = true;
                    }
                    if (lines.size() < LOCK_WAIT_EVIDENCE_ROWS) {
                        // DIGEST_TEXT 可能包含业务字面量，必须脱敏后才能进入证据。
                        lines.add("digest=" + SqlSanitizer.sanitize(resultSet.getString("DIGEST_TEXT"))
                                + " count=" + resultSet.getLong("COUNT_STAR")
                                + " total_seconds=" + totalSeconds);
                    }
                }
                String summary = "采集到 " + rows + " 条语句摘要；前 " + lines.size() + " 行: "
                        + String.join(" | ", lines);
                return new DatabaseCheck(SLOW_SQL, overThreshold ? STATUS_WARNING : STATUS_OK,
                        SLOW_SQL_SQL, bounded(summary, limits), rows, collectedAt.toString());
            }
        } catch (SQLException e) {
            if (isMissingObject(e)) {
                return new DatabaseCheck(SLOW_SQL, STATUS_DATA_MISSING, SLOW_SQL_SQL,
                        bounded("performance_schema.events_statements_summary_by_digest 不可用: "
                                + brief(e), limits), 0, collectedAt.toString());
            }
            return new DatabaseCheck(SLOW_SQL, STATUS_FAILED, SLOW_SQL_SQL,
                    bounded("慢 SQL 摘要查询失败: " + brief(e), limits), 0, collectedAt.toString());
        }
    }

    private DatabaseCheck checkReplicationLag(Connection connection, DatabaseQueryLimits limits) {
        String sql = "SHOW REPLICA STATUS";
        Instant collectedAt = Instant.now();
        try (PreparedStatement statement = prepare(connection, sql, limits)) {
            boolean hasResult = statement.execute();
            if (!hasResult) {
                return new DatabaseCheck(REPLICATION_LAG, STATUS_NOT_APPLICABLE, sql,
                        "当前实例不是复制从库（SHOW REPLICA STATUS 无结果集）", 0, collectedAt.toString());
            }
            try (ResultSet resultSet = statement.getResultSet()) {
                if (resultSet == null || !resultSet.next()) {
                    return new DatabaseCheck(REPLICATION_LAG, STATUS_NOT_APPLICABLE, sql,
                            "当前实例不是复制从库（SHOW REPLICA STATUS 为空）", 0, collectedAt.toString());
                }
                Map<String, String> row = readRow(resultSet);
                String seconds = firstNonNull(row, "seconds_behind_source", "seconds_behind_master");
                if (seconds == null && !row.containsKey("seconds_behind_source")
                        && !row.containsKey("seconds_behind_master")) {
                    return new DatabaseCheck(REPLICATION_LAG, STATUS_DATA_MISSING, sql,
                            bounded("复制状态缺少 Seconds_Behind_Source 列", limits), 1, collectedAt.toString());
                }
                String ioRunning = firstNonNull(row, "replica_io_running", "slave_io_running");
                String sqlRunning = firstNonNull(row, "replica_sql_running", "slave_sql_running");
                if (seconds == null) {
                    return new DatabaseCheck(REPLICATION_LAG, STATUS_WARNING, sql,
                            bounded("复制延迟未知：Seconds_Behind_Source 为 NULL（复制线程未运行）"
                                    + " Replica_IO_Running=" + ioRunning
                                    + " Replica_SQL_Running=" + sqlRunning, limits),
                            1, collectedAt.toString());
                }
                long lag = parseLong(seconds);
                if (lag > REPLICATION_LAG_WARNING_SECONDS) {
                    return new DatabaseCheck(REPLICATION_LAG, STATUS_WARNING, sql,
                            bounded("复制延迟 " + lag + " 秒，超过阈值 "
                                    + REPLICATION_LAG_WARNING_SECONDS + " 秒"
                                    + " Replica_IO_Running=" + ioRunning
                                    + " Replica_SQL_Running=" + sqlRunning, limits),
                            1, collectedAt.toString());
                }
                return new DatabaseCheck(REPLICATION_LAG, STATUS_OK, sql,
                        bounded("复制延迟 " + lag + " 秒，在阈值内"
                                + " Replica_IO_Running=" + ioRunning
                                + " Replica_SQL_Running=" + sqlRunning, limits),
                        1, collectedAt.toString());
            }
        } catch (SQLException e) {
            String message = e.getMessage() == null ? "" : e.getMessage().toLowerCase(Locale.ROOT);
            String state = e.getSQLState() == null ? "" : e.getSQLState();
            if ("42000".equals(state) || message.contains("not supported")
                    || message.contains("syntax error") || isMissingObject(e)) {
                return new DatabaseCheck(REPLICATION_LAG, STATUS_DATA_MISSING, sql,
                        bounded("当前实例不支持 SHOW REPLICA STATUS: " + brief(e), limits),
                        0, collectedAt.toString());
            }
            return new DatabaseCheck(REPLICATION_LAG, STATUS_FAILED, sql,
                    bounded("复制状态查询失败: " + brief(e), limits), 0, collectedAt.toString());
        }
    }

    /* ── 辅助 ─────────────────────────────────────────────────────────── */

    private static PreparedStatement prepare(Connection connection, String sql, DatabaseQueryLimits limits)
            throws SQLException {
        // 单语句 + 只读校验：任何进入驱动的诊断 SQL 都必须先过守卫。
        ReadOnlySqlGuard.requireReadOnly(sql);
        PreparedStatement statement = connection.prepareStatement(sql);
        statement.setQueryTimeout(Math.max(1, limits.timeoutSeconds()));
        statement.setMaxRows(Math.max(1, limits.maxRows()));
        return statement;
    }

    private static Map<String, String> readRow(ResultSet resultSet) throws SQLException {
        Map<String, String> row = new LinkedHashMap<>();
        ResultSetMetaData metaData = resultSet.getMetaData();
        for (int index = 1; index <= metaData.getColumnCount(); index++) {
            row.put(metaData.getColumnLabel(index).toLowerCase(Locale.ROOT), resultSet.getString(index));
        }
        return row;
    }

    private static String firstNonNull(Map<String, String> row, String... keys) {
        for (String key : keys) {
            if (row.containsKey(key) && row.get(key) != null) {
                return row.get(key);
            }
        }
        return null;
    }

    private static long parseLong(String value) {
        try {
            return Long.parseLong(value.trim());
        } catch (NumberFormatException e) {
            return -1L;
        }
    }

    /** performance_schema 表/列缺失：归为 DATA_MISSING，而不是把"没开采集"当成故障。 */
    private static boolean isMissingObject(SQLException e) {
        String state = e.getSQLState() == null ? "" : e.getSQLState();
        if ("42S02".equals(state) || "42S22".equals(state) || "42S21".equals(state)) {
            return true;
        }
        String message = e.getMessage() == null ? "" : e.getMessage().toLowerCase(Locale.ROOT);
        return message.contains("doesn't exist") || message.contains("unknown table")
                || message.contains("unknown column") || message.contains("not found")
                || message.contains("syntax error");
    }

    private static String brief(SQLException e) {
        String message = e.getMessage() == null ? "" : e.getMessage().replace('\n', ' ').replace('\r', ' ').trim();
        String state = e.getSQLState() == null ? "" : " [SQLState " + e.getSQLState() + "]";
        String text = message + state;
        return text.length() <= 200 ? text : text.substring(0, 200) + "...";
    }

    /** 证据字节预算：超限直接截断并标注，保留"证据不完整"这一事实。 */
    private static String bounded(String evidence, DatabaseQueryLimits limits) {
        if (evidence == null) {
            return "";
        }
        int maxBytes = Math.max(64, limits.maxBytes());
        byte[] bytes = evidence.getBytes(StandardCharsets.UTF_8);
        if (bytes.length <= maxBytes) {
            return evidence;
        }
        int keep = Math.max(0, maxBytes - "[TRUNCATED]".length());
        return new String(bytes, 0, keep, StandardCharsets.UTF_8) + "[TRUNCATED]";
    }
}
