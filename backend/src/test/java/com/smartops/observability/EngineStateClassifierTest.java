package com.smartops.observability;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * T37：心跳超时判定的诚实性内核。覆盖 6 类状态 + 边界值。
 */
class EngineStateClassifierTest {

    private final EngineStateClassifier classifier = new EngineStateClassifier();
    private static final long NOW = 1_800_000_000L;

    private EngineStateClassifier.EngineFacts facts(
            String id, Long lastAt, long count, boolean success, String summary) {
        return new EngineStateClassifier.EngineFacts(id, lastAt, count, success, summary);
    }

    @Test
    @DisplayName("无事件（count=0）→ NO_DATA，age=0，不造假")
    void noData() {
        var s = classifier.classify(facts("inspector", null, 0, true, null), NOW);
        assertThat(s.status()).isEqualTo(EngineCatalog.Status.NO_DATA);
        assertThat(s.ageSec()).isZero();
        assertThat(s.lastEventAtText()).isEqualTo("—");
        assertThat(s.detail()).contains("无数据");
    }

    @Test
    @DisplayName("最后事件=now → RUNNING")
    void freshRunning() {
        var s = classifier.classify(facts("sentinel-poll", NOW, 12, true, "采集成功"), NOW);
        assertThat(s.status()).isEqualTo(EngineCatalog.Status.RUNNING);
        assertThat(s.ageSec()).isZero();
        assertThat(s.detail()).contains("距上次心跳 0s / 阈值 30s");
    }

    @Test
    @DisplayName("边界 age==period 仍 RUNNING")
    void boundaryRunning() {
        var s = classifier.classify(facts("sentinel-poll", NOW - 30, 12, true, "ok"), NOW);
        assertThat(s.status()).isEqualTo(EngineCatalog.Status.RUNNING);
    }

    @Test
    @DisplayName("period+1 → STALLED，detail 可解释")
    void justStalled() {
        var s = classifier.classify(facts("sentinel-poll", NOW - 31, 12, true, "ok"), NOW);
        assertThat(s.status()).isEqualTo(EngineCatalog.Status.STALLED);
        assertThat(s.detail()).contains("疑似停摆", "31s", "30s");
    }

    @Test
    @DisplayName("边界 age==5×period → STALLED 非长期")
    void boundaryFiveTimes() {
        var s = classifier.classify(facts("sentinel-poll", NOW - 150, 12, true, "ok"), NOW);
        assertThat(s.status()).isEqualTo(EngineCatalog.Status.STALLED);
        assertThat(s.detail()).doesNotContain("长期无心跳");
    }

    @Test
    @DisplayName("5×period+1 → STALLED 且标长期无心跳")
    void longIdle() {
        var s = classifier.classify(facts("sentinel-poll", NOW - 151, 12, true, "ok"), NOW);
        assertThat(s.status()).isEqualTo(EngineCatalog.Status.STALLED);
        assertThat(s.detail()).contains("长期无心跳", "5 倍");
    }

    @Test
    @DisplayName("最近事件失败 → ERROR，优先于新鲜度")
    void errorOverridesFresh() {
        var s = classifier.classify(facts("web-research", NOW, 5, false, "error_code=TIMEOUT"), NOW);
        assertThat(s.status()).isEqualTo(EngineCatalog.Status.ERROR);
        assertThat(s.detail()).contains("最近事件异常");
    }

    @Test
    @DisplayName("training 恒 NOT_RUN，不因伪造事件变绿")
    void trainingNotRun() {
        var s = classifier.classify(facts("training", NOW, 999, true, "伪造"), NOW);
        assertThat(s.status()).isEqualTo(EngineCatalog.Status.NOT_RUN);
        assertThat(s.detail()).contains("未运行");
    }

    @Test
    @DisplayName("未来时间戳（时钟漂移）不产生负 age")
    void futureTimestamp() {
        var s = classifier.classify(facts("inspector", NOW + 100, 3, true, "ok"), NOW);
        assertThat(s.status()).isEqualTo(EngineCatalog.Status.RUNNING);
        assertThat(s.ageSec()).isZero();
    }

    @Test
    @DisplayName("未知引擎 id 抛异常，防绕过白名单")
    void unknownIdRejected() {
        assertThatThrownBy(() -> classifier.classify(facts("evil;drop", NOW, 1, true, "x"), NOW))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
