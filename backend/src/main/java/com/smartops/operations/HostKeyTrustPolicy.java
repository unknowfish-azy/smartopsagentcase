package com.smartops.operations;

import com.smartops.entity.OperationKnownHost;
import com.smartops.entity.OperationSession;

public class HostKeyTrustPolicy {
    private final KnownHostStore store;

    public HostKeyTrustPolicy(KnownHostStore store) {
        this.store = store;
    }

    public boolean allows(OperationSession session, PresentedHostKey key, HostKeyDecision decision) {
        if (decision == HostKeyDecision.TRUST_ONCE || decision == HostKeyDecision.TRUST_AND_SAVE) {
            return true;
        }
        return store.find(session.getId(), key.host(), key.port())
                .map(saved -> matches(saved, key))
                .orElse(false);
    }

    public void save(OperationSession session, PresentedHostKey key) {
        OperationKnownHost knownHost = new OperationKnownHost();
        knownHost.setSessionId(session.getId());
        knownHost.setHost(key.host());
        knownHost.setPort(key.port());
        knownHost.setAlgorithm(key.algorithm());
        knownHost.setFingerprint(key.fingerprint());
        knownHost.setPublicKey(key.publicKey());
        store.save(knownHost);
    }

    private static boolean matches(OperationKnownHost saved, PresentedHostKey key) {
        return saved.getHost().equals(key.host())
                && saved.getPort().equals(key.port())
                && saved.getAlgorithm().equals(key.algorithm())
                && saved.getFingerprint().equals(key.fingerprint())
                && saved.getPublicKey().equals(key.publicKey());
    }
}
