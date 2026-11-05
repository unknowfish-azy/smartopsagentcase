package com.smartops.cloud;

/**
 * 云访问凭据（仅在内存中使用）。
 *
 * toString 显式脱敏：异常、日志、审计里即使误把该对象拼进字符串，
 * 也不会带出 accessKeySecret。
 */
public record CloudCredentials(String accessKeyId, String accessKeySecret) {

    @Override
    public String toString() {
        return "CloudCredentials[accessKeyId=" + mask(accessKeyId) + ", accessKeySecret=***]";
    }

    private static String mask(String value) {
        if (value == null || value.isBlank()) {
            return "***";
        }
        return value.length() <= 4 ? "***" : "***" + value.substring(value.length() - 4);
    }
}
