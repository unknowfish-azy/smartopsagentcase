package com.smartops.ensplab;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.ArrayList;
import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * /api/ensp 接口的 standalone MockMvc 验证：不加载 Spring 上下文，因此不需要数据库 / Redis。
 */
class EnsPLabApiTest {

    private MockMvc mvc;
    private EnspModels.Experiment experiment;

    @BeforeEach
    void setUp() {
        EnspKnowledgeBase kb = new EnspKnowledgeBase();
        EnspLabService service = new EnspLabService(kb, new TopologyParser(kb), new ConfigValidator(kb));
        mvc = MockMvcBuilders.standaloneSetup(new EnspLabController(service)).build();
        experiment = kb.experiments().stream()
                .map(EnspKnowledgeBase.ExperimentHit::experiment)
                .filter(e -> e.topologyId() != null && !e.topologyId().isBlank())
                .findFirst()
                .orElseThrow();
    }

    @Test
    void overviewReturnsTextbookCounts() throws Exception {
        mvc.perform(get("/api/ensp/overview"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.counts.modules").value(8))
                .andExpect(jsonPath("$.data.counts.knowledgePoints").value(40))
                .andExpect(jsonPath("$.data.counts.experiments").value(42))
                .andExpect(jsonPath("$.data.modules.length()").value(8));
    }

    @Test
    void moduleDetailIncludesTopologyAndAnswers() throws Exception {
        String moduleId = experiment.moduleId();
        mvc.perform(get("/api/ensp/modules/{id}", moduleId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.module.id").value(moduleId));
    }

    @Test
    void knowledgeSearchFiltersByKeyword() throws Exception {
        mvc.perform(get("/api/ensp/knowledge").param("keyword", "VLAN"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.length()").value(org.hamcrest.Matchers.greaterThan(0)));
    }

    @Test
    void experimentDetailCarriesTopologyGraph() throws Exception {
        mvc.perform(get("/api/ensp/experiments/{id}", experiment.id()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.experiment.id").value(experiment.id()))
                .andExpect(jsonPath("$.data.topology.devices.length()")
                        .value(org.hamcrest.Matchers.greaterThan(0)));
    }

    @Test
    void validateConfigMarksExpectedCommandsAsPass() throws Exception {
        List<String> lines = new ArrayList<>();
        for (EnspModels.Step step : experiment.steps()) {
            lines.addAll(step.commands());
        }
        StringBuilder body = new StringBuilder("{\"experimentId\":\"")
                .append(experiment.id()).append("\",\"lines\":[");
        for (int i = 0; i < lines.size(); i++) {
            if (i > 0) {
                body.append(',');
            }
            body.append('"').append(lines.get(i).replace("\\", "\\\\").replace("\"", "\\\"")).append('"');
        }
        body.append("]}");

        mvc.perform(post("/api/ensp/validate-config")
                        .contentType("application/json").content(body.toString()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.pass").value(true))
                .andExpect(jsonPath("$.data.score").value(100));
    }

    @Test
    void validateFlagsWrongContext() throws Exception {
        String body = "{\"lines\":[\"system-view\",\"port link-type access\"],\"context\":\"user\"}";
        mvc.perform(post("/api/ensp/validate").contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.lines[1].status").value("WRONG_CONTEXT"));
    }

    @Test
    void topologyEndpointReturnsParsedGraph() throws Exception {
        mvc.perform(get("/api/ensp/topologies/{id}", experiment.topologyId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.devices.length()").value(org.hamcrest.Matchers.greaterThan(0)))
                .andExpect(jsonPath("$.data.links").exists());
    }
}
