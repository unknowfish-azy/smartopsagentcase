package com.smartops.diagnostics.database;

import com.smartops.exception.BusinessException;
import org.springframework.stereotype.Component;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

/**
 * 基于 JDBC URL 的连接提供者（OPS-07）。
 *
 * <p>URL 中固定关闭多语句与 SSL（内网只读诊断），并把单语句超时同时映射到
 * {@code socketTimeout} 与 {@code connectTimeout}，避免网络抖动时挂死诊断线程。</p>
 */
@Component
public class DriverManagerConnectionProvider implements DatabaseConnectionProvider {

    @Override
    public Connection open(DatabaseTarget target, String username, String password) throws SQLException {
        if (target.engine() != DatabaseEngine.MYSQL) {
            throw new BusinessException(400, "DATABASE_ENGINE_NOT_IMPLEMENTED: " + target.engine().name()
                    + " 适配器尚未实现");
        }
        int timeoutMs = Math.max(1, target.timeoutSeconds()) * 1000;
        String url = "jdbc:mysql://" + target.host() + ":" + target.port() + "/" + target.database()
                + "?useSSL=false&allowMultiQueries=false&socketTimeout=" + timeoutMs
                + "&connectTimeout=" + timeoutMs + "&serverTimezone=UTC";
        return DriverManager.getConnection(url, username, password);
    }
}
