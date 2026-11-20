package com.smartops.guard;

/** 单条用例的判定结果。ERROR 表示没有拿到有效响应，不计为 PASS。 */
public enum GuardVerdict {
    PASS,
    FAIL,
    ERROR;

    public static GuardVerdict parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return ERROR;
        }
        try {
            return GuardVerdict.valueOf(raw.trim().toUpperCase(java.util.Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            return ERROR;
        }
    }
}
