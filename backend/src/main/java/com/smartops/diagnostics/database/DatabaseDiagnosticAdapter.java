package com.smartops.diagnostics.database;

import java.sql.Connection;
import java.util.List;

/**
 * 数据库诊断适配器（OPS-07）。
 *
 * <p>按引擎实现；PostgreSQL / openGauss 先只保留接口，不注册实现，
 * 由服务层给出 {@code DATABASE_ENGINE_NOT_IMPLEMENTED}。</p>
 */
public interface DatabaseDiagnosticAdapter {

    DatabaseEngine engine();

    List<DatabaseCheck> diagnose(Connection connection, DatabaseQueryLimits limits);
}
