package com.smartops.diagnostics.database;

import java.sql.Connection;
import java.sql.SQLException;

/**
 * 数据库连接提供者（OPS-07）。
 *
 * <p>抽出接口是为了让测试可以注入 H2 连接，同时生产实现保持"按引擎拼 URL"的唯一入口。</p>
 */
public interface DatabaseConnectionProvider {

    Connection open(DatabaseTarget target, String username, String password) throws SQLException;
}
