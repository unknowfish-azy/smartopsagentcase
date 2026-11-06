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
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
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

    /** SEC-08：读侧从会话主体取身份；测试用 Authentication 作为 request principal。 */
    private static org.springframework.security.core.Authentication login() {
        return new org.springframework.security.authentication.UsernamePasswordAuthenticationToken(
                new com.smartops.security.SessionUser(7L, "u7", "user", "user", false, 0), null, List.of());
    }

    @Test
    void summaryUsesExistingApiEnvelope() throws Exception {
        when(service.summary(any(), anyBoolean())).thenReturn(Map.of("total", 0, "pass", 0));

        mockMvc.perform(get("/api/inspector/summary").principal(login()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.total").value(0));
    }

    @Test
    void eventsReturnsPersistedReadModel() throws Exception {
        when(service.events(anyInt(), any(), anyBoolean())).thenReturn(List.of(
                Map.of("id", "INS-001", "status", "PASS")
        ));

        mockMvc.perform(get("/api/inspector/events").principal(login()))
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
