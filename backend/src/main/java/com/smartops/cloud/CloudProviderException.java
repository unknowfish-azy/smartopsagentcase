package com.smartops.cloud;

/**
 * 云厂商调用失败。
 *
 * code 是稳定分类（CLOUD_PERMISSION_DENIED / CLOUD_RATE_LIMITED / ...），
 * message 只放可对外展示的信息：不含凭据、不含 Authorization 头、不含请求体。
 */
public class CloudProviderException extends RuntimeException {

    private final String code;
    private final boolean permissionDenied;

    public CloudProviderException(String code, String message) {
        this(code, message, false, null);
    }

    public CloudProviderException(String code, String message, boolean permissionDenied, Throwable cause) {
        super(message, cause);
        this.code = code;
        this.permissionDenied = permissionDenied;
    }

    public String code() {
        return code;
    }

    public boolean permissionDenied() {
        return permissionDenied;
    }
}
