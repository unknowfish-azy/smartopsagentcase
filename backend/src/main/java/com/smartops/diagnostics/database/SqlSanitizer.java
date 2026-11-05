package com.smartops.diagnostics.database;

import java.util.regex.Pattern;

/**
 * SQL 脱敏（OPS-07）。
 *
 * <p>慢 SQL 的 DIGEST_TEXT 与诊断语句在进入证据前都要过这里：剥离注释、
 * 把字符串字面量与数字替换为 {@code ?}，保证输出中不出现业务数据原文，
 * 最终截断到 300 字符，避免一条超长 SQL 撑爆证据字段。</p>
 */
public final class SqlSanitizer {

    static final int MAX_LENGTH = 300;

    private static final Pattern BLOCK_COMMENT = Pattern.compile("/\\*.*?\\*/", Pattern.DOTALL);
    private static final Pattern LINE_COMMENT = Pattern.compile("--[^\n\r]*");
    private static final Pattern SINGLE_QUOTED = Pattern.compile("'(?:[^']|'')*'");
    private static final Pattern DOUBLE_QUOTED = Pattern.compile("\"(?:[^\"]|\"\")*\"");
    private static final Pattern NUMBER = Pattern.compile("\\b\\d+(\\.\\d+)?\\b");
    private static final Pattern WHITESPACE = Pattern.compile("\\s+");

    private SqlSanitizer() {
    }

    public static String sanitize(String sql) {
        if (sql == null || sql.isBlank()) {
            return "";
        }
        String text = BLOCK_COMMENT.matcher(sql).replaceAll(" ");
        text = LINE_COMMENT.matcher(text).replaceAll(" ");
        text = SINGLE_QUOTED.matcher(text).replaceAll("?");
        text = DOUBLE_QUOTED.matcher(text).replaceAll("?");
        text = NUMBER.matcher(text).replaceAll("?");
        text = WHITESPACE.matcher(text).replaceAll(" ").trim();
        return text.length() <= MAX_LENGTH ? text : text.substring(0, MAX_LENGTH);
    }
}
