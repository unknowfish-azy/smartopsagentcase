package com.smartops.operations;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;

class OperationConnectionCoordinatorTest {
    @Test
    void fiftyConcurrentConnectsEstablishOnlyOneRuntime() throws Exception {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry(200, 200);
        OperationConnectionCoordinator coordinator = new OperationConnectionCoordinator(registry);
        AtomicInteger dials = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(50);
        List<ConnectionResult> results = new ArrayList<>();
        List<String> runtimeIds = new ArrayList<>();

        try {
            for (int index = 0; index < 50; index++) {
                pool.submit(() -> {
                    start.await();
                    ConnectionResult result = coordinator.establish(7L, 70L, () -> {
                        dials.incrementAndGet();
                        try {
                            Thread.sleep(80);
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                        }
                        String runtimeId = registry.register(
                                new OperationRuntimeRegistryTest.StubRuntime(7L, 70L, true));
                        return ConnectionResult.online(runtimeId, null, null);
                    });
                    synchronized (results) {
                        results.add(result);
                        runtimeIds.add(result.runtimeId());
                    }
                    return null;
                });
            }
            start.countDown();
            pool.shutdown();
            assertThat(pool.awaitTermination(30, TimeUnit.SECONDS)).isTrue();
        } finally {
            pool.shutdownNow();
        }

        assertThat(dials.get()).isEqualTo(1);
        assertThat(results).hasSize(50);
        assertThat(results).allMatch(result -> "ONLINE".equals(result.status()));
        assertThat(runtimeIds.stream().distinct().count()).isEqualTo(1);
        Optional<String> indexed = registry.findBySession(7L, 70L);
        assertThat(indexed).isPresent().contains(runtimeIds.get(0));
    }

    @Test
    void reusesExistingLiveRuntimeWithoutDialingAgain() {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        OperationConnectionCoordinator coordinator = new OperationConnectionCoordinator(registry);
        String runtimeId = registry.register(new OperationRuntimeRegistryTest.StubRuntime(3L, 30L, true));

        ConnectionResult result = coordinator.establish(3L, 30L, () -> {
            throw new AssertionError("不应在已有存活通道时再次拨号");
        });

        assertThat(result.status()).isEqualTo("ONLINE");
        assertThat(result.runtimeId()).isEqualTo(runtimeId);
        assertThat(result.reused()).isTrue();
    }
}
