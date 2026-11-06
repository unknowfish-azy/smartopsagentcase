package com.smartops.operations;

public record ConnectionResult(
        String status,
        String runtimeId,
        String stage,
        String fingerprint,
        String algorithm,
        String message,
        boolean reused) {
    public ConnectionResult(String status, String runtimeId, String stage, String fingerprint,
                            String algorithm, String message) {
        this(status, runtimeId, stage, fingerprint, algorithm, message, false);
    }
    public static ConnectionResult online(String runtimeId, String fingerprint, String algorithm) {
        return new ConnectionResult("ONLINE", runtimeId, "CHANNEL", fingerprint, algorithm, null);
    }
    /** 同用户同会话已有存活通道：直接复用，没有重新拨号。 */
    public static ConnectionResult reused(String runtimeId) {
        return new ConnectionResult("ONLINE", runtimeId, "CHANNEL", null, null, null, true);
    }
    public static ConnectionResult hostKeyRequired(String fingerprint, String algorithm) {
        return new ConnectionResult("HOST_KEY_REQUIRED", null, "HOST_KEY", fingerprint, algorithm, "Explicit trust decision required");
    }
    public static ConnectionResult failed(String stage, String message) {
        return new ConnectionResult("CONNECT_FAILED", null, stage, null, null, message);
    }
}
