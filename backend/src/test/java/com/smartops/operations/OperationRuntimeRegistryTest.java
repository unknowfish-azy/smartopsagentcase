package com.smartops.operations;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.time.Instant;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OperationRuntimeRegistryTest {
    @Test
    void indexesRuntimeByUserAndSessionForReuse() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        String runtimeId = registry.register(new StubRuntime(1L, 11L, true));

        Optional<String> found = registry.findBySession(1L, 11L);
        assertThat(found).contains(runtimeId);

        registry.removeOwned(runtimeId, 1L);
        assertThat(registry.findBySession(1L, 11L)).isEmpty();
        assertThat(registry.size()).isZero();
    }

    @Test
    void enforcesPerUserQuotaAndClosesNothingOnRejection() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry(2, 4);
        registry.register(new StubRuntime(1L, 1L, true));
        registry.register(new StubRuntime(1L, 2L, true));

        assertThatThrownBy(() -> registry.register(new StubRuntime(1L, 3L, true)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("RUNTIME_QUOTA_EXCEEDED");
        assertThat(registry.size()).isEqualTo(2);
    }

    @Test
    void enforcesPerSessionQuota() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry(10, 1);
        registry.register(new StubRuntime(1L, 8L, true));

        assertThatThrownBy(() -> registry.register(new StubRuntime(1L, 8L, true)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("RUNTIME_SESSION_LIMIT_EXCEEDED");
    }

    @Test
    void sweepClosesIdleRuntimeAndDropsIndex() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        StubRuntime runtime = new StubRuntime(1L, 21L, true);
        String runtimeId = registry.register(runtime);

        long ttl = 1_000L;
        int removed = registry.sweep(Instant.now().plusMillis(ttl + 5_000L), ttl);

        assertThat(removed).isEqualTo(1);
        assertThat(runtime.closed).isTrue();
        assertThat(registry.size()).isZero();
        assertThat(registry.findBySession(1L, 21L)).isEmpty();
        assertThat(runtimeId).isNotBlank();
    }

    @Test
    void sweepRemovesClosedRuntime() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        StubRuntime runtime = new StubRuntime(1L, 31L, false);
        registry.register(runtime);

        int removed = registry.sweep(Instant.now(), 900_000L);

        assertThat(removed).isEqualTo(1);
        assertThat(registry.size()).isZero();
    }

    @Test
    void findSessionIgnoresClosedRuntime() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        StubRuntime runtime = new StubRuntime(1L, 41L, true);
        String runtimeId = registry.register(runtime);
        runtime.open = false;

        assertThat(registry.findBySession(1L, 41L)).isEmpty();
        assertThat(registry.size()).isZero();
        assertThat(runtimeId).isNotBlank();
    }

    static final class StubRuntime implements OperationRuntime {
        private final Long userId;
        private final Long sessionId;
        private volatile boolean open;
        private volatile boolean closed;

        StubRuntime(Long userId, Long sessionId, boolean open) {
            this.userId = userId;
            this.sessionId = sessionId;
            this.open = open;
        }

        @Override public String id() { return "stub"; }
        @Override public Long userId() { return userId; }
        @Override public Long sessionId() { return sessionId; }
        @Override public void write(String input) throws IOException { }
        @Override public void resize(int columns, int rows) throws IOException { }
        @Override public void onOutput(OutputListener listener) { }
        @Override public boolean isOpen() { return open; }
        @Override public void close() { closed = true; open = false; }
    }
}
