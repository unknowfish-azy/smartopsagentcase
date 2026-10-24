package com.smartops.operations;

public record ConnectionResult(
        String status,
        String runtimeId,
        String stage,
        String fingerprint,
        String algorithm,
        String message) {
    public static ConnectionResult online(String runtimeId, String fingerprint, String algorithm) {
        return new ConnectionResult("ONLINE", runtimeId, "CHANNEL", fingerprint, algorithm, null);
    }
    public static ConnectionResult hostKeyRequired(String fingerprint, String algorithm) {
        return new ConnectionResult("HOST_KEY_REQUIRED", null, "HOST_KEY", fingerprint, algorithm, "Explicit trust decision required");
    }
    public static ConnectionResult failed(String stage, String message) {
        return new ConnectionResult("CONNECT_FAILED", null, stage, null, null, message);
    }
}
