package com.smartops.operations;

public record PresentedHostKey(String host, int port, String algorithm, String fingerprint, String publicKey) {
}
