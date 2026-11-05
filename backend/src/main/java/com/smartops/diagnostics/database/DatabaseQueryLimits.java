package com.smartops.diagnostics.database;

/** 单次诊断的查询预算：行数、单语句超时与证据字节上限（OPS-07）。 */
public record DatabaseQueryLimits(int maxRows, int timeoutSeconds, int maxBytes) {
}
