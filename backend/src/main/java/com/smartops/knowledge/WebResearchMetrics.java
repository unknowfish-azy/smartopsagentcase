package com.smartops.knowledge;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * 联网研究可观测指标（T35c，Micrometer）。
 *
 * <p>全部绑真实事件：无事件即零，不做假繁忙；不含任何金额/评分类指标。
 * 指标走 management.metrics 既有 prometheus 暴露，不新增依赖。</p>
 */
@Component
public class WebResearchMetrics {

    private final MeterRegistry registry;

    public WebResearchMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void radarDue() {
        registry.counter("smartops.webresearch.radar.due").increment();
    }

    public void radarProcessed() {
        registry.counter("smartops.webresearch.radar.processed").increment();
    }

    public void radarSkipped() {
        registry.counter("smartops.webresearch.radar.skipped").increment();
    }

    /** T41：雷达抓取触发 JS 渲染降级的次数（真实计数，无事件即零）。 */
    public void radarJsFallback() {
        registry.counter("smartops.webresearch.radar.js_fallback").increment();
    }

    public void snapshotWritten() {
        registry.counter("smartops.webresearch.snapshot.written").increment();
    }

    public void retentionDeleted(long count) {
        if (count > 0) registry.counter("smartops.webresearch.retention.deleted").increment(count);
    }

    public void renderDuration(Duration duration) {
        registry.timer("smartops.webresearch.render.duration").record(duration);
    }
}
