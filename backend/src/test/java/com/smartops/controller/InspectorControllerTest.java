package com.smartops.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.inspector.InspectionRecordRequest;
import com.smartops.service.InspectorEventService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InspectorController.class)
@AutoConfigureMockMvc(addFilters = false)
class InspectorControllerTest {
    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private InspectorEventService service;

    @Test
    void summaryUsesExistingApiEnvelope() throws Exception {
        when(service.summary()).thenReturn(Map.of("total", 0, "pass", 0));

        mockMvc.perform(get("/api/inspector/summary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.total").value(0));
    }

    @Test
    void eventsReturnsPersistedReadModel() throws Exception {
        when(service.events(50)).thenReturn(List.of(
                Map.of("id", "INS-001", "status", "PASS")
        ));

        mockMvc.perform(get("/api/inspector/events"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].id").value("INS-001"));
    }

    @Test
    void checkValidatesAndPersistsInspectionResult() throws Exception {
        InspectionRecordRequest request = new InspectionRecordRequest();
        request.setTaskId("TASK-001");
        request.setStatus("PASS");
        request.setSeverity("INFO");
        request.setReason("全部检查通过");

        when(service.record(any())).thenReturn(
                Map.of("id", "INS-001", "status", "PASS")
        );

        mockMvc.perform(post("/api/inspector/check")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.id").value("INS-001"));
    }
}
