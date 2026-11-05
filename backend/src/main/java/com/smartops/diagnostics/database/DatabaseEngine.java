package com.smartops.diagnostics.database;

import com.smartops.exception.BusinessException;

import java.util.Locale;

/**
 * 数据库诊断引擎（OPS-07）。
 *
 * <p>{@code implemented=false} 的引擎只做接口预留：调用方拿到的是稳定错误码，
 * 而不是"看起来能跑、连上去才发现没适配"。</p>
 */
public enum DatabaseEngine {

    MYSQL(true, null),
    POSTGRESQL(false, "PostgreSQL 适配器尚未实现：仅预留 DatabaseDiagnosticAdapter 接口，未做联调"),
    OPENGAUSS(false, "openGauss 适配器尚未实现：仅预留 DatabaseDiagnosticAdapter 接口，未做联调");

    private final boolean implemented;
    private final String unavailableReason;

    DatabaseEngine(boolean implemented, String unavailableReason) {
        this.implemented = implemented;
        this.unavailableReason = unavailableReason;
    }

    public boolean implemented() {
        return implemented;
    }

    public String unavailableReason() {
        return unavailableReason;
    }

    /** 大小写不敏感解析；非法引擎一律 400，避免拼写错误被当成"未知引擎跳过诊断"。 */
    public static DatabaseEngine parse(String value) {
        if (value == null || value.isBlank()) {
            throw new BusinessException(400, "DATABASE_ENGINE_INVALID");
        }
        String normalized = value.trim().toUpperCase(Locale.ROOT);
        for (DatabaseEngine engine : values()) {
            if (engine.name().equals(normalized)) {
                return engine;
            }
        }
        throw new BusinessException(400, "DATABASE_ENGINE_INVALID");
    }
}
