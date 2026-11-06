package com.smartops.operations;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 敏感数据统一脱敏（SEC-11）。
 *
 * <p>覆盖 {@code key=value}、{@code key: value}、JSON 形态、{@code Bearer} 令牌与
 * PEM 私钥块；用于工具输出落库/回显、爬取正文、巡检证据等所有“写库前”边界。
 * 只做保守替换（命中即遮蔽），不做格式化修复，避免把原文带回来。</p>
 */
public final class OperationRedactor {
    public static final String MASK = "[REDACTED]";

    /** 敏感键名基线：password/token/secret/api_key/authorization/cookie/私钥/会话。 */
    private static final String KEYS = "password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
            + "private[_-]?key|client[_-]?secret|authorization|cookie|credential|session[_-]?id";

    /** 值：带引号（可跨行）或裸值；裸值允许内嵌 {@code Bearer } 前缀。 */
    private static final String VALUE = "\"(?:[^\"\\\\]|\\\\.)*\"|'(?:[^'\\\\]|\\\\.)*'|(?:Bearer\\s+)?[^\\s,;&}\\]]+";

    private static final Pattern PRIVATE_KEY = Pattern.compile(
            "-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", Pattern.DOTALL);

    private static final Pattern ASSIGNMENT = Pattern.compile(
            "(?i)((?:" + KEYS + ")\"?\\s*(?:=|:)\\s*)(" + VALUE + ")");

    private static final Pattern BEARER = Pattern.compile("(?i)(Bearer\\s+)([A-Za-z0-9._~+/=-]+)");

    private OperationRedactor() {}

    public static String redact(String value) {
        if (value == null || value.isEmpty()) return value;
        String masked = PRIVATE_KEY.matcher(value).replaceAll(MASK);
        masked = maskAssignments(masked);
        return BEARER.matcher(masked).replaceAll("$1" + MASK);
    }

    /** 键保留、值替换；键名在 JSON 中时补引号，避免把元数据 JSON 打成非法结构。 */
    private static String maskAssignments(String value) {
        Matcher matcher = ASSIGNMENT.matcher(value);
        StringBuilder out = new StringBuilder();
        while (matcher.find()) {
            String prefix = matcher.group(1);
            String replacement = prefix.indexOf('"') >= 0 ? "\"" + MASK + "\"" : MASK;
            matcher.appendReplacement(out, Matcher.quoteReplacement(prefix + replacement));
        }
        matcher.appendTail(out);
        return out.toString();
    }
}
