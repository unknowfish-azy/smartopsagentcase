package com.smartops.diagnostics.database;

/** 数据库连接目标；不包含任何凭据（OPS-07）。 */
public record DatabaseTarget(DatabaseEngine engine, String host, int port, String database, int timeoutSeconds) {
}
