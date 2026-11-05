package com.smartops.diagnostics.database;

import jakarta.validation.constraints.NotBlank;

/**
 * 数据库诊断入参（OPS-07）。
 *
 * <p>超时与行数在构造时夹紧：调用方传 0 或越界值时回落到安全默认，
 * 避免"诊断本身把生产库拖慢"。</p>
 */
public record DatabaseDiagnosisRequest(
        @NotBlank String engine,
        @NotBlank String host,
        int port,
        @NotBlank String database,
        @NotBlank String credentialRef,
        Long teamId,
        int timeoutSeconds,
        int maxRows) {

    private static final int DEFAULT_TIMEOUT_SECONDS = 10;
    private static final int MAX_TIMEOUT_SECONDS = 30;
    private static final int DEFAULT_MAX_ROWS = 200;
    private static final int MAX_ROWS = 1000;

    public DatabaseDiagnosisRequest {
        timeoutSeconds = timeoutSeconds <= 0
                ? DEFAULT_TIMEOUT_SECONDS
                : Math.min(MAX_TIMEOUT_SECONDS, timeoutSeconds);
        maxRows = maxRows <= 0
                ? DEFAULT_MAX_ROWS
                : Math.min(MAX_ROWS, maxRows);
    }
}
