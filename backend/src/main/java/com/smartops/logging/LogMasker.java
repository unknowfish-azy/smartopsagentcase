package com.smartops.logging;

import java.util.regex.Pattern;

/**
 * SEC-11 日志脱敏工具：把日志文本中的敏感片段替换为 ***。
 * 供 {@link MaskingConverter}（消息）与 {@link MaskingThrowableProxyConverter}（异常栈）共用。
 */
final class LogMasker {

    private static final Pattern BEARER = Pattern.compile(
            "(?i)(Bearer\\s+)[A-Za-z0-9._\\-]+");

    private static final Pattern URL_PARAM = Pattern.compile(
            "(?i)([?&](?:api[_-]?key|apikey|key|token|password|pwd|secret|access[_-]?token)=)[^&\\s\"']+");

    private static final Pattern JSON_FIELD = Pattern.compile(
            "(?i)(\"(?:password|pwd|api[_-]?key|apikey|token|secret|access[_-]?token)\"\\s*:\\s*\")[^\"]*(\")");

    private static final String MASK = "***";

    private LogMasker() {}

    static String mask(String input) {
        if (input == null || input.isEmpty()) return input;
        String masked = BEARER.matcher(input).replaceAll("$1" + MASK);
        masked = URL_PARAM.matcher(masked).replaceAll("$1" + MASK);
        masked = JSON_FIELD.matcher(masked).replaceAll("$1" + MASK + "$2");
        return masked;
    }
}
