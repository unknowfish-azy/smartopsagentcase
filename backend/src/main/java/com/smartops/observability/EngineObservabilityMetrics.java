package com.smartops.observability;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * 引擎可观测大屏的调用指标（T38）。
 *
 * <p>仿 WebResearchMetrics：只绑真实调用，无请求即零，不新增依赖、不含假繁忙。</p>
 */
@Component
public class EngineObservabilityMetrics {

    private final MeterRegistry registry;

    public EngineObservabilityMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void snapshotRequested() {
        registry.counter("smartops.engineobs.snapshot.requested").increment();
    }

    public void streamRequested() {
        registry.counter("smartops.engineobs.stream.requested").increment();
    }

    public void snapshotDuration(Duration duration) {
        registry.timer("smartops.engineobs.snapshot.duration").record(duration);
    }
}
