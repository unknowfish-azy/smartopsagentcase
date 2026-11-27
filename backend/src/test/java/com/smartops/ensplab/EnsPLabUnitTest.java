package com.smartops.ensplab;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * eNSP 知识库 / 拓扑解析 / 配置校验的基础回归测试。
 *
 * <p>不加载 Spring 上下文，直接实例化三个组件，保证知识库资源与规则库在类路径上可用。</p>
 */
class EnsPLabUnitTest {

    private final EnspKnowledgeBase kb = new EnspKnowledgeBase();
    private final TopologyParser parser = new TopologyParser(kb);
    private final ConfigValidator validator = new ConfigValidator(kb);

    @Test
    void knowledgeBaseLoadsComplete() {
        assertEquals(8, kb.modules().size());
        assertEquals(40, kb.knowledgePoints().size());
        assertEquals(42, kb.experiments().size());
        assertFalse(kb.manifest().topologies().isEmpty());
        assertTrue(kb.rules().rules().size() >= 80);
    }

    @Test
    void validatesCommandLineWithPromptsAndEchoes() {
        List<String> input = List.of(
                "<Huawei>system-view",
                "Enter system view, return user view with Ctrl+Z.",
                "[Huawei]sysname SWA",
                "[SWA]vlan batch 10 20",
                "[SWA]interface GigabitEthernet 0/0/1",
                "[SWA-GigabitEthernet0/0/1]port link-type access",
                "[SWA-GigabitEthernet0/0/1]port default vlan 10",
                "[SWA-GigabitEthernet0/0/1]quit",
                "[SWA]interface Vlanif 10",
                "[SWA-Vlanif10]ip address 192.168.10.1 24",
                "[SWA-Vlanif10]return",
                "<SWA>ping 192.168.10.2");
        ConfigValidator.ValidationReport report = validator.validate(input, "user");
        assertEquals("user", report.context());
        assertEquals(100, report.score());
        assertTrue(report.lines().stream().noneMatch(l -> l.status().equals("UNKNOWN")));
    }

    @Test
    void flagsWrongContextUnknownAndAbbreviation() {
        ConfigValidator.LineResult wrong = validator.checkLine("[SWA]port link-type access", "system");
        assertEquals("WRONG_CONTEXT", wrong.status());

        ConfigValidator.LineResult unknown = validator.checkLine("frobnicate", "system");
        assertEquals("UNKNOWN", unknown.status());

        ConfigValidator.LineResult abbreviated = validator.checkLine("<Huawei>sy", "user");
        assertEquals("OK", abbreviated.status());
        assertEquals("system", abbreviated.contextAfter());
    }

    @Test
    void comparesInputWithExperimentSteps() {
        EnspModels.Experiment experiment = kb.experiments().get(0).experiment();
        List<String> correct = new ArrayList<>();
        for (EnspModels.Step step : experiment.steps()) {
            correct.addAll(step.commands());
        }
        ConfigValidator.ValidationReport pass = validator.validateExperiment(experiment.id(), correct);
        assertTrue(pass.pass());
        assertEquals(100, pass.score());
        assertTrue(pass.missing().isEmpty());
        assertTrue(pass.steps().stream().allMatch(ConfigValidator.StepProgress::done));

        ConfigValidator.ValidationReport empty = validator.validateExperiment(experiment.id(), List.of());
        assertFalse(empty.pass());
        assertTrue(empty.score() < 100);
        assertFalse(empty.missing().isEmpty());
        assertFalse(empty.suggestions().isEmpty());
    }

    @Test
    void parsesTopologyReferencedByExperiment() {
        EnspModels.Experiment experiment = kb.experiments().stream()
                .map(EnspKnowledgeBase.ExperimentHit::experiment)
                .filter(e -> e.topologyId() != null && !e.topologyId().isBlank())
                .findFirst()
                .orElseThrow();
        TopologyParser.TopologyGraph graph = parser.parse(experiment.topologyId());
        assertNotNull(graph);
        assertFalse(graph.devices().isEmpty());
        assertFalse(graph.links().isEmpty());
    }
}
