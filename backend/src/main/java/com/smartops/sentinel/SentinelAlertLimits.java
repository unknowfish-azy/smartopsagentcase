package com.smartops.sentinel;

/** 冻结文本与日志的截断上限，避免把超大输出写进数据库。 */
public final class SentinelAlertLimits {

    private SentinelAlertLimits() {}

    /** 执行输出只保留尾部：先看得到失败原因，比保留开头的 banner 更有用。 */
    public static String truncate(String value, int max) {
        if (value == null) return null;
        return value.length() <= max ? value : value.substring(0, max);
    }
}
