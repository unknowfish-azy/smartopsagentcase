package com.smartops.operations;

import com.smartops.entity.OperationKnownHost;
import com.smartops.entity.OperationSession;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class HostKeyTrustPolicyTest {

    private final OperationSession session = session(41L, "ops.example.test", 2222);
    private final PresentedHostKey key = new PresentedHostKey(
            "ops.example.test", 2222, "ssh-ed25519", "SHA256:trusted", "AAAAC3NzaC1lZDI1NTE5AAAAITest");

    @Test
    void requires_an_explicit_decision_for_an_unknown_key() {
        InMemoryKnownHostStore store = new InMemoryKnownHostStore();
        HostKeyTrustPolicy policy = new HostKeyTrustPolicy(store);

        assertThat(policy.allows(session, key, HostKeyDecision.NONE)).isFalse();
    }

    @Test
    void trusts_a_key_once_without_persisting_it() {
        InMemoryKnownHostStore store = new InMemoryKnownHostStore();
        HostKeyTrustPolicy policy = new HostKeyTrustPolicy(store);

        assertThat(policy.allows(session, key, HostKeyDecision.TRUST_ONCE)).isTrue();
        assertThat(store.find(session.getId(), key.host(), key.port())).isEmpty();
    }

    @Test
    void saves_a_trusted_key_for_a_fresh_policy_instance() {
        InMemoryKnownHostStore store = new InMemoryKnownHostStore();
        HostKeyTrustPolicy firstPolicy = new HostKeyTrustPolicy(store);

        firstPolicy.save(session, key);

        HostKeyTrustPolicy restartedPolicy = new HostKeyTrustPolicy(store);
        assertThat(restartedPolicy.allows(session, key, HostKeyDecision.NONE)).isTrue();
    }

    @Test
    void requires_a_new_decision_when_a_saved_key_changes() {
        InMemoryKnownHostStore store = new InMemoryKnownHostStore();
        HostKeyTrustPolicy policy = new HostKeyTrustPolicy(store);
        policy.save(session, key);
        PresentedHostKey changedKey = new PresentedHostKey(
                "ops.example.test", 2222, "ssh-ed25519", "SHA256:changed", "AAAAC3NzaC1lZDI1NTE5AAAAIChanged");

        assertThat(policy.allows(session, changedKey, HostKeyDecision.NONE)).isFalse();
    }

    private static OperationSession session(Long id, String host, int port) {
        OperationSession session = new OperationSession();
        session.setId(id);
        session.setHost(host);
        session.setPort(port);
        return session;
    }

    private static final class InMemoryKnownHostStore implements KnownHostStore {
        private final Map<String, OperationKnownHost> entries = new HashMap<>();

        @Override
        public Optional<OperationKnownHost> find(Long sessionId, String host, int port) {
            return Optional.ofNullable(entries.get(sessionId + ":" + host + ":" + port));
        }

        @Override
        public void save(OperationKnownHost knownHost) {
            entries.put(knownHost.getSessionId() + ":" + knownHost.getHost() + ":" + knownHost.getPort(), knownHost);
        }
    }
}
