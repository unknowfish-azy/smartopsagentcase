package com.smartops.sentinel;

import com.smartops.service.OperatorMemoryService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * DistillExperienceService 单测。
 *
 * <p>蒸馏只在满足全部前置条件时触发：</p>
 * <ul>
 *   <li>trigger_kind = ALERT（手动/定时不算告警处置）</li>
 *   <li>result = SUCCESS 或 FAILED（最终态，不是 PENDING/RUNNING）</li>
 *   <li>基本字段齐全（alertId, metric, scriptName）</li>
 * </ul>
 */
class DistillExperienceServiceTest {

    private static final long RUN_ID = 5001L;
    private static final long USER_ID = 22L;

    private JdbcTemplate jdbc;
    private OperatorMemoryService memories;
    private DistillExperienceService distill;

    @BeforeEach
    void setup() {
        jdbc = mock(JdbcTemplate.class);
        memories = mock(OperatorMemoryService.class);
        distill = new DistillExperienceService(jdbc, memories);
    }

    /** 模拟 loadRunSnapshot 返回指定字段。 */
    private void mockRunSnapshot(String triggerKind, String result, String metric, String severity, String scriptName) {
        java.util.HashMap<String, Object> row = new java.util.HashMap<>();
        row.put("trigger_kind", triggerKind);
        row.put("result", result);
        row.put("actor_id", USER_ID);
        row.put("alert_id", 9001L);
        row.put("script_name", scriptName);
        row.put("metric", metric);
        row.put("severity", severity);
        when(jdbc.queryForList(anyString(), eq(RUN_ID))).thenReturn(List.of(row));
    }

    /* ── 触发蒸馏的正面场景 ──────────────────────────────────────── */

    @Test
    @DisplayName("ALERT 触发 + SUCCESS → 蒸馏一条 DECISION_LOOP 记忆")
    void alertSuccess_distilled() {
        mockRunSnapshot("ALERT", "SUCCESS", "cpu_usage", "P2", "nginx-restart");

        distill.distillAfterRun(RUN_ID);

        verify(memories).recordLearned(eq(USER_ID),
                eq("sentinel:cpu_usage:P2"),                       // incident_key
                anyString(),                                        // preferred_action
                eq("SCRIPT_RUN:" + RUN_ID));                        // source_refs 幂等键
    }

    @Test
    @DisplayName("ALERT 触发 + FAILED → 也蒸馏（失败也是经验）")
    void alertFailed_distilledToo() {
        mockRunSnapshot("ALERT", "FAILED", "disk_usage", "P1", "disk-cleanup");

        distill.distillAfterRun(RUN_ID);

        verify(memories).recordLearned(eq(USER_ID),
                eq("sentinel:disk_usage:P1"), anyString(),
                eq("SCRIPT_RUN:" + RUN_ID));
    }

    @Test
    @DisplayName("SUCCESS 后 preferred_action 包含成功/失败 + 可执行规则")
    void actionContainsCausalChain() {
        mockRunSnapshot("ALERT", "SUCCESS", "memory", "P2", "memory-cleanup");

        distill.distillAfterRun(RUN_ID);

        verify(memories).recordLearned(eq(USER_ID), anyString(),
                org.mockito.ArgumentMatchers.contains("成功"),
                anyString());
        verify(memories).recordLearned(eq(USER_ID), anyString(),
                org.mockito.ArgumentMatchers.contains("memory"),
                anyString());
        verify(memories).recordLearned(eq(USER_ID), anyString(),
                org.mockito.ArgumentMatchers.contains("memory-cleanup"),
                anyString());
    }

    @Test
    @DisplayName("severity 为 null 时 incident_key 不含 severity（降级）")
    void nullSeverity_graceful() {
        mockRunSnapshot("ALERT", "SUCCESS", "cpu_usage", null, "nginx-restart");

        distill.distillAfterRun(RUN_ID);

        verify(memories).recordLearned(eq(USER_ID),
                eq("sentinel:cpu_usage"), anyString(), anyString());
    }

    /* ── 跳过蒸馏的负面场景 ──────────────────────────────────────── */

    @Test
    @DisplayName("trigger_kind = MANUAL → 不蒸馏（手动执行不算告警处置）")
    void manualRun_notDistilled() {
        mockRunSnapshot("MANUAL", "SUCCESS", "cpu_usage", "P2", "nginx-restart");
        distill.distillAfterRun(RUN_ID);
        verify(memories, never()).recordLearned(anyLong(), anyString(), anyString(), anyString());
    }

    @Test
    @DisplayName("trigger_kind = SCHEDULE → 不蒸馏（定时执行不算告警处置）")
    void scheduleRun_notDistilled() {
        mockRunSnapshot("SCHEDULE", "SUCCESS", "cpu_usage", "P2", "nginx-restart");
        distill.distillAfterRun(RUN_ID);
        verify(memories, never()).recordLearned(anyLong(), anyString(), anyString(), anyString());
    }

    @Test
    @DisplayName("result = PENDING_APPROVAL → 不蒸馏（非最终态）")
    void pendingApproval_notDistilled() {
        mockRunSnapshot("ALERT", "PENDING_APPROVAL", "cpu_usage", "P2", "nginx-restart");
        distill.distillAfterRun(RUN_ID);
        verify(memories, never()).recordLearned(anyLong(), anyString(), anyString(), anyString());
    }

    @Test
    @DisplayName("result = RUNNING → 不蒸馏（非最终态）")
    void running_notDistilled() {
        mockRunSnapshot("ALERT", "RUNNING", "cpu_usage", "P2", "nginx-restart");
        distill.distillAfterRun(RUN_ID);
        verify(memories, never()).recordLearned(anyLong(), anyString(), anyString(), anyString());
    }

    @Test
    @DisplayName("result = CANCELLED → 不蒸馏（非最终态）")
    void cancelled_notDistilled() {
        mockRunSnapshot("ALERT", "CANCELLED", "cpu_usage", "P2", "nginx-restart");
        distill.distillAfterRun(RUN_ID);
        verify(memories, never()).recordLearned(anyLong(), anyString(), anyString(), anyString());
    }

    @Test
    @DisplayName("找不到 run 记录 → 静默跳过")
    void runNotFound_skip() {
        when(jdbc.queryForList(anyString(), eq(RUN_ID))).thenReturn(List.of());
        distill.distillAfterRun(RUN_ID);
        verify(memories, never()).recordLearned(anyLong(), anyString(), anyString(), anyString());
    }

    @Test
    @DisplayName("metric 缺失 → 跳过蒸馏")
    void nullMetric_skip() {
        mockRunSnapshot("ALERT", "SUCCESS", null, "P2", "nginx-restart");
        distill.distillAfterRun(RUN_ID);
        verify(memories, never()).recordLearned(anyLong(), anyString(), anyString(), anyString());
    }

    @Test
    @DisplayName("memory.recordLearned 抛错 → 静默（主链路不挂）")
    void memoryError_silent() {
        mockRunSnapshot("ALERT", "SUCCESS", "cpu_usage", "P2", "nginx-restart");
        when(memories.recordLearned(anyLong(), anyString(), anyString(), anyString()))
                .thenThrow(new RuntimeException("DB gone"));
        // 不抛异常就是通过
        distill.distillAfterRun(RUN_ID);
    }
}
