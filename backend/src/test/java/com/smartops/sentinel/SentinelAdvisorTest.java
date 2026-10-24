package com.smartops.sentinel;

import com.smartops.service.IncidentRecommendationService;
import com.smartops.service.OperatorMemoryService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 告警研判（AI 辅助建议）测试。
 *
 * <p>重点不在"文案好不好看"，而在几件必须成立的事：
 * 建议可解释、低风险脚本优先、高风险必须提示人工、结论不能被当成既定事实。</p>
 */
class SentinelAdvisorTest {

    private static final long USER = 7L;

    private static SentinelAdvisor advisor(OperatorMemoryService memories) {
        return new SentinelAdvisor(new IncidentRecommendationService(), memories);
    }

    /** 空记忆替身：分析逻辑本身不依赖数据库。 */
    private static OperatorMemoryService noMemories() {
        OperatorMemoryService memories = org.mockito.Mockito.mock(OperatorMemoryService.class);
        org.mockito.Mockito.when(memories.list(org.mockito.ArgumentMatchers.anyLong())).thenReturn(List.of());
        return memories;
    }

    private static OperatorMemoryService withMemory(String incidentKey, String action) {
        OperatorMemoryService memories = org.mockito.Mockito.mock(OperatorMemoryService.class);
        org.mockito.Mockito.when(memories.list(org.mockito.ArgumentMatchers.anyLong())).thenReturn(List.of(
                new OperatorMemoryService.Memory(1L, USER, incidentKey, "REMEDIATION", action, "run:42", 3, 0.8, "ACTIVE",
                        Instant.parse("2026-10-01T00:00:00Z"), Instant.parse("2026-10-01T00:00:00Z"))));
        return memories;
    }

    private static SentinelAdvisor.AlertFacts alert(String severity, String title, String metric) {
        return new SentinelAdvisor.AlertFacts(1L, severity, title, metric, "95.0", "memory > 90", "{\"memory\":95.0}");
    }

    @Test
    @DisplayName("按脚本名称与标签匹配候选，并给出可解释理由")
    void recommendsScriptsWithExplainableReason() {
        // 标题里刻意不含 web：标签匹配是子串匹配，"web-01" 里的 web 会命中 web 标签，
        // 那是**预期行为**（宁可多给一个候选，也不漏掉相关脚本）。这里单独验证名称命中。
        var advice = advisor(noMemories()).analyze(alert("P2", "app-01：内存使用率越界", "memory"),
                List.of(new SentinelAdvisor.ScriptFact(1L, "memory-cleanup", "cache,cleanup", "LOW"),
                        new SentinelAdvisor.ScriptFact(2L, "nginx-restart", "web", "MEDIUM"),
                        new SentinelAdvisor.ScriptFact(3L, "unrelated-script", "billing", "LOW")),
                USER);
        assertEquals(1, advice.scripts().size(), "只有名称命中 memory 的脚本才是候选");
        assertEquals(1L, advice.scripts().get(0).scriptId());
        assertTrue(advice.scripts().get(0).reason().contains("memory"), "理由必须指出命中了什么");
    }

    @Test
    @DisplayName("标签子串命中也会进入候选（宁可多给，不漏相关脚本）")
    void tagSubstringMatchesCount() {
        var advice = advisor(noMemories()).analyze(alert("P2", "web-01：内存使用率越界", "memory"),
                List.of(new SentinelAdvisor.ScriptFact(2L, "nginx-restart", "web", "MEDIUM")), USER);
        assertEquals(1, advice.scripts().size());
        assertTrue(advice.scripts().get(0).reason().contains("web"));
    }

    @Test
    @DisplayName("低风险脚本排在前面：推荐顺序本身在表达先试低危的")
    void lowRiskScriptsComeFirst() {
        var advice = advisor(noMemories()).analyze(alert("P2", "memory 越界 memory", "memory"),
                List.of(new SentinelAdvisor.ScriptFact(10L, "memory-high", "memory", "HIGH"),
                        new SentinelAdvisor.ScriptFact(11L, "memory-low", "memory", "LOW"),
                        new SentinelAdvisor.ScriptFact(12L, "memory-mid", "memory", "MEDIUM")),
                USER);
        assertEquals(List.of(11L, 12L, 10L), advice.scripts().stream().map(SentinelAdvisor.ScriptCandidate::scriptId).toList());
    }

    @Test
    @DisplayName("P0/P1 或含高风险候选时，明确提示人工优先介入")
    void highRiskRequiresHumanFirst() {
        assertTrue(advisor(noMemories()).analyze(alert("P0", "memory 越界", "memory"), List.of(), USER).humanFirst());
        assertTrue(advisor(noMemories()).analyze(alert("P1", "memory 越界", "memory"), List.of(), USER).humanFirst());
        assertTrue(advisor(noMemories()).analyze(alert("P3", "memory 越界", "memory"),
                List.of(new SentinelAdvisor.ScriptFact(1L, "memory-wipe", "memory", "HIGH")), USER).humanFirst());
        assertFalse(advisor(noMemories()).analyze(alert("P3", "memory 越界", "memory"),
                List.of(new SentinelAdvisor.ScriptFact(1L, "memory-low", "memory", "LOW")), USER).humanFirst());
    }

    @Test
    @DisplayName("有既往记忆时把经验并入建议，并说明来源")
    void usesOperatorMemory() {
        var advice = advisor(withMemory("memory", "先清理缓存再观察")).analyze(
                alert("P2", "memory 越界", "memory"), List.of(), USER);
        assertFalse(advice.memoryMatches().isEmpty());
        assertEquals("先清理缓存再观察", advice.memoryMatches().get(0).action());
        assertTrue(advice.summary().contains("先清理缓存再观察"));
    }

    @Test
    @DisplayName("没有任何记忆与候选时如实说明需要人工判断，而不是编一个建议")
    void statesLackOfEvidenceHonestly() {
        var advice = advisor(noMemories()).analyze(alert("P2", "disk 越界", "disk"), List.of(), USER);
        assertTrue(advice.scripts().isEmpty());
        assertTrue(advice.memoryMatches().isEmpty());
        assertTrue(advice.summary().contains("人工判断"));
        assertFalse(advice.humanFirst(), "P2 且无高风险候选时不需要强制人工前置");
    }

    @Test
    @DisplayName("研判结论始终标注为建议，附证据与免责声明")
    void alwaysLabelledAsAdvice() {
        var advice = advisor(noMemories()).analyze(alert("P2", "memory 越界", "memory"), List.of(), USER);
        assertFalse(advice.evidence().isEmpty(), "必须能看到证据");
        assertNotNull(advice.disclaimer());
        assertTrue(advice.disclaimer().contains("建议"));
        assertTrue(advice.disclaimer().contains("审批"));
        assertFalse(advice.disclaimer().contains("已执行"), "免责声明不能暗示已执行任何动作");
    }

    @Test
    @DisplayName("脚本名称过短或无关时不产生噪音候选")
    void ignoresWeakMatches() {
        var advice = advisor(noMemories()).analyze(alert("P2", "memory 越界", "memory"),
                List.of(new SentinelAdvisor.ScriptFact(1L, "a", "b", "LOW"),
                        new SentinelAdvisor.ScriptFact(2L, "disk-sweep", "disk", "LOW")), USER);
        assertTrue(advice.scripts().isEmpty(), "3 字符以下的词与无关脚本都不应被推荐");
    }
}
