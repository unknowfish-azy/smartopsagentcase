package com.smartops.observability;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 引擎可观测大屏的引擎目录（T37）。
 *
 * <p>每条引擎声明：真实事件源表、时间列、成功判定列、预期周期。
 * 全部事实来自已存在的表，不新增表、不改造 poller。</p>
 *
 * <p>⚠️ 本类是 SQL 唯一来源：表名/列名全部写死在此，禁止拼接外部输入。
 * training 无真实训练事件表，显式标 NOT_RUN，不造假。</p>
 */
public final class EngineCatalog {

    public enum Status {
        NO_DATA, RUNNING, STALLED, ERROR, NOT_RUN
    }

    /** 引擎目录项。 */
    public record EngineDef(
            String id,
            String name,
            String table,
            String timeColumn,
            String successColumn,
            long expectedPeriodSec,
            boolean notRun) {
    }

    private static final Map<String, EngineDef> DEFS = build();

    private static Map<String, EngineDef> build() {
        Map<String, EngineDef> m = new LinkedHashMap<>();
        m.put("sentinel-poll", new EngineDef(
                "sentinel-poll", "哨兵巡检", "sentinel_task", "last_seen_at", "last_status", 30, false));
        m.put("sentinel-guardian", new EngineDef(
                "sentinel-guardian", "守护 Agent", "sentinel_alert_event", "at", "kind", 60, false));
        m.put("web-research", new EngineDef(
                "web-research", "联网研究", "web_research_task", "finished_at", "error_code", 90, false));
        m.put("inspector", new EngineDef(
                "inspector", "纠察", "inspector_event", "created_at", "status", 300, false));
        m.put("decision-loop", new EngineDef(
                "decision-loop", "决策闭环", "agent_decision_loop", "created_at", "outcome", 300, false));
        m.put("operation-run", new EngineDef(
                "operation-run", "运维执行", "operation_run_record", "ended_at", "status", 300, false));
        m.put("training", new EngineDef(
                "training", "模型训练", null, null, null, 0, true));
        return Collections.unmodifiableMap(m);
    }

    /** 展示顺序（training 恒在最后）。 */
    public static List<EngineDef> ordered() {
        return Arrays.asList(
                get("sentinel-poll"), get("sentinel-guardian"), get("web-research"),
                get("inspector"), get("decision-loop"), get("operation-run"), get("training"));
    }

    public static EngineDef get(String id) {
        return DEFS.get(id);
    }

    public static boolean isValid(String id) {
        return DEFS.containsKey(id);
    }

    public static java.util.Collection<String> ids() {
        return DEFS.keySet();
    }

    private EngineCatalog() {
    }
}
