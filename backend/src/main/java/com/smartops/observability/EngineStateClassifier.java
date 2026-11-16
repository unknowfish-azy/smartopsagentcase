package com.smartops.observability;

import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

/**
 * 引擎状态判定（T37，纯逻辑）。
 *
 * <p>铁律：状态只由真实事件事实推导，无事件即静默。
 * ERROR 优先于时间新鲜度；摸鱼=心跳超时，且 detail 必须给出可解释的"距上次 Xs/阈值 Ys"，
 * 绝不伪造繁忙或合成心跳。</p>
 */
@Component
public class EngineStateClassifier {

    private static final DateTimeFormatter TS =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss").withZone(ZoneId.systemDefault());
    /** 超过 5× 预期周期标记为长期无心跳。 */
    static final long LONG_IDLE_FACTOR = 5;

    /** 判定所需的真实事实（由 Service 从真实表聚合，无合成值）。 */
    public record EngineFacts(
            String id,
            Long lastEventAtEpochSec, // null = 该表从无事件
            long eventCount,
            boolean lastEventSuccess,
            String lastEventSummary) {
    }

    /** 判定结果（下发前端，字段全部可解释）。 */
    public record EngineState(
            String id,
            String name,
            EngineCatalog.Status status,
            Long lastEventAtEpochSec,
            String lastEventAtText,
            long ageSec,
            long expectedPeriodSec,
            long eventCount,
            String lastEventSummary,
            String detail) {
    }

    /**
     * 纯函数：由事实 + 当前时间判定状态。无副作用、不读库、不读时钟（now 由调用方注入）。
     */
    public EngineState classify(EngineFacts facts, long nowEpochSec) {
        EngineCatalog.EngineDef def = EngineCatalog.get(facts.id());
        if (def == null) {
            throw new IllegalArgumentException("unknown engine id: " + facts.id());
        }

        if (def.notRun()) {
            return state(facts, def, EngineCatalog.Status.NOT_RUN, 0,
                    "未运行 · 无真实训练事件源");
        }

        long count = facts.eventCount();
        if (count <= 0 || facts.lastEventAtEpochSec() == null) {
            return state(facts, def, EngineCatalog.Status.NO_DATA, 0,
                    "无数据 · 该引擎事件源暂无真实记录");
        }

        long age = Math.max(0, nowEpochSec - facts.lastEventAtEpochSec());
        long period = def.expectedPeriodSec();

        // ERROR 优先：最近一条真实事件本身失败，即使时间新鲜也判异常。
        if (!facts.lastEventSuccess()) {
            return state(facts, def, EngineCatalog.Status.ERROR, age,
                    "最近事件异常 · 距上次 " + age + "s（阈值 " + period + "s）");
        }

        if (age <= period) {
            return state(facts, def, EngineCatalog.Status.RUNNING, age,
                    "运行中 · 距上次心跳 " + age + "s / 阈值 " + period + "s");
        }

        long factor = age / Math.max(1, period);
        String detail;
        if (age > LONG_IDLE_FACTOR * period) {
            detail = "长期无心跳 · 距上次 " + age + "s / 阈值 " + period
                    + "s（超 " + factor + " 倍）";
        } else {
            detail = "疑似停摆 · 距上次 " + age + "s / 阈值 " + period + "s";
        }
        return state(facts, def, EngineCatalog.Status.STALLED, age, detail);
    }

    private EngineState state(EngineFacts facts, EngineCatalog.EngineDef def,
                              EngineCatalog.Status status, long age, String detail) {
        Long ts = facts.lastEventAtEpochSec();
        String text = ts == null ? "—" : TS.format(Instant.ofEpochSecond(ts));
        String summary = facts.lastEventSummary() == null || facts.lastEventSummary().isBlank()
                ? "—" : facts.lastEventSummary();
        return new EngineState(
                facts.id(), def.name(), status, ts, text, age,
                def.expectedPeriodSec(), facts.eventCount(), summary, detail);
    }
}
