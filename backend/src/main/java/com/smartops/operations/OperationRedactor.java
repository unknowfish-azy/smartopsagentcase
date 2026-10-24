package com.smartops.operations;

import java.util.regex.Pattern;

public final class OperationRedactor {
    private static final Pattern SECRET = Pattern.compile(
            "(?i)(password|passwd|token|secret|api[_-]?key|private[_-]?key)\\s*(=|:)\\s*([^\\s]+)");

    private OperationRedactor() {}

    public static String redact(String value) {
        if (value == null) return null;
        return SECRET.matcher(value).replaceAll("$1$2[REDACTED]");
    }
}
