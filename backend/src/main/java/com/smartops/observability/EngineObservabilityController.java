package com.smartops.observability;

import com.smartops.common.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
// List 供 Snapshot record 使用

/**
 * 引擎可观测大屏只读接口（T38）。
 *
 * <p>鉴权沿用全局 internalTokenAuthenticationFilter + 登录态，与 /api/sentinel/** 一致。
 * 无任何写操作，不暴露新数据面。</p>
 */
@RestController
@RequestMapping("/api/engine-observability")
public class EngineObservabilityController {

    private final EngineSnapshotService snapshot;
    private final EngineStateClassifier classifier;
    private final EngineObservabilityMetrics metrics;

    public EngineObservabilityController(EngineSnapshotService snapshot,
                                         EngineStateClassifier classifier,
                                         EngineObservabilityMetrics metrics) {
        this.snapshot = snapshot;
        this.classifier = classifier;
        this.metrics = metrics;
    }

    public record EventItem(Long at, String kind, String summary) {
    }

    public record Snapshot(Long generatedAt, List<EngineStateClassifier.EngineState> engines) {
    }

    /** 六/七条引擎的运行时快照。 */
    @GetMapping("/snapshot")
    public ApiResponse<Snapshot> snapshot() {
        long start = System.nanoTime();
        metrics.snapshotRequested();
        long now = Instant.now().getEpochSecond();
        List<EngineStateClassifier.EngineState> states = new ArrayList<>();
        for (EngineStateClassifier.EngineFacts facts : snapshot.collectAll()) {
            states.add(classifier.classify(facts, now));
        }
        metrics.snapshotDuration(Duration.ofNanos(System.nanoTime() - start));
        return ApiResponse.success(new Snapshot(now, states));
    }

    /** 指定引擎最近 N 条真实事件；engine 必须命中白名单。 */
    @GetMapping("/event-stream")
    public ApiResponse<?> eventStream(
            @RequestParam String engine,
            @RequestParam(defaultValue = "50") int limit) {
        metrics.streamRequested();
        if (!EngineCatalog.isValid(engine)) {
            return ApiResponse.error(400, "unknown engine: " + engine);
        }
        // 统一结构：合法引擎（含 training 空事件）都返回 {engine, events}。
        return ApiResponse.success(Map.of("engine", engine, "events", snapshot.eventStream(engine, limit)));
    }
}
