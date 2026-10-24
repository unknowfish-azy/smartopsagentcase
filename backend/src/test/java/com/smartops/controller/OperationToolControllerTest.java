package com.smartops.controller;

import com.smartops.service.OperationToolService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class OperationToolControllerTest {
    private OperationToolService service;
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        service = mock(OperationToolService.class);
        mvc = MockMvcBuilders.standaloneSetup(new OperationToolController(service)).build();
    }

    @Test
    void previews_a_server_defined_tool() throws Exception {
        when(service.preview(eq(7L), eq("host-health"), any()))
                .thenReturn(new OperationToolService.ToolPreview("host-health", true, List.of("uptime")));

        mvc.perform(post("/api/operations/tools/preview")
                        .header("X-User-Id", "7")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"toolId\":\"host-health\",\"parameters\":{}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.toolId").value("host-health"))
                .andExpect(jsonPath("$.data.commands[0]").value("uptime"));
    }

    @Test
    void lists_function_call_tool_security_metadata() throws Exception {
        when(service.listTools()).thenReturn(List.of(
                new OperationToolService.ToolDescriptor("host-health", true, "LOW", false, "HOST_HEALTH"),
                new OperationToolService.ToolDescriptor("service-restart", false, "HIGH", true, "SERVICE_RESTART")
        ));

        mvc.perform(get("/api/operations/tools"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].toolId").value("host-health"))
                .andExpect(jsonPath("$.data[0].readOnly").value(true))
                .andExpect(jsonPath("$.data[1].requireConfirm").value(true));
    }

    @Test
    void executes_a_tool_against_an_owned_runtime() throws Exception {
        Instant now = Instant.parse("2026-09-27T00:00:00Z");
        var command = new OperationToolService.ToolCommandResult("uptime", 0, "up", "", now, now);
        var result = new OperationToolService.ToolRunResult("trace-1", "runtime-1", "host-health", "SUCCEEDED", List.of(command), now, now);
        when(service.execute(eq(7L), eq("runtime-1"), eq("host-health"), any())).thenReturn(result);

        mvc.perform(post("/api/operations/runtimes/runtime-1/tools/host-health/execute")
                        .header("X-User-Id", "7")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"parameters\":{}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.traceId").value("trace-1"))
                .andExpect(jsonPath("$.data.commands[0].exitCode").value(0));
    }
}
