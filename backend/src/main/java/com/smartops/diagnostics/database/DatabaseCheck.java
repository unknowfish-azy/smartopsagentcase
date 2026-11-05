package com.smartops.diagnostics.database;

/**
 * 单条数据库检查结果（OPS-07）。
 *
 * <p>{@code sql} 必须是脱敏后的语句，{@code status} 取
 * {@code OK / WARNING / FAILED / DATA_MISSING / NOT_APPLICABLE}。
 * 采集不到与真实故障必须分开：DATA_MISSING 不是 FAILED。</p>
 */
public record DatabaseCheck(String name, String status, String sql, String evidence,
                            int rowCount, String collectedAt) {

    public DatabaseCheck {
        sql = SqlSanitizer.sanitize(sql);
        evidence = evidence == null ? "" : evidence;
    }
}
