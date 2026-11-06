package com.smartops.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.IncidentCreateRequest;
import com.smartops.module.incident.IncidentSeverity;
import com.smartops.module.incident.IncidentSource;
import com.smartops.module.incident.IncidentStatus;
import com.smartops.service.IncidentService;
import com.smartops.vo.IncidentVO;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(IncidentController.class)
@AutoConfigureMockMvc(addFilters = false)
class IncidentControllerTest {

    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;

    @Autowired private MockMvc mockMvc;
    @Autowired private ObjectMapper objectMapper;
    @MockBean private IncidentService incidentService;

    @Test
    void createIncidentShouldSuccess() throws Exception {
        IncidentVO vo = IncidentVO.builder()
                .id(1L)
                .title("CPU 过高")
                .status(IncidentStatus.OPEN)
                .severity(IncidentSeverity.P1)
                .source(IncidentSource.ALERT)
                .build();

        when(incidentService.create(any(IncidentCreateRequest.class))).thenReturn(vo);

        IncidentCreateRequest request = new IncidentCreateRequest();
        request.setTitle("CPU 过高");
        request.setSeverity(IncidentSeverity.P1);
        request.setSource(IncidentSource.ALERT);

        mockMvc.perform(post("/api/incidents")
                        .contentType(APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.id").value(1))
                .andExpect(jsonPath("$.data.status").value("OPEN"));
    }

    @Test
    void createWithEmptyTitleShouldReturn400() throws Exception {
        IncidentCreateRequest request = new IncidentCreateRequest();
        request.setTitle("");

        mockMvc.perform(post("/api/incidents")
                        .contentType(APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(400));
    }

    @Test
    void getByIdShouldReturnIncident() throws Exception {
        IncidentVO vo = IncidentVO.builder()
                .id(1L)
                .title("测试事件")
                .status(IncidentStatus.OPEN)
                .severity(IncidentSeverity.P2)
                .build();
        when(incidentService.getById(1L)).thenReturn(vo);

        mockMvc.perform(get("/api/incidents/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.title").value("测试事件"));
    }

    @Test
    void acknowledgeShouldTransitionToAck() throws Exception {
        IncidentVO vo = IncidentVO.builder()
                .id(1L)
                .status(IncidentStatus.ACK)
                .build();
        when(incidentService.acknowledge(eq(1L), any())).thenReturn(vo);

        mockMvc.perform(post("/api/incidents/1/acknowledge?actorId=10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("ACK"));
    }

    @Test
    void createFromAlertShouldReturnIncident() throws Exception {
        IncidentVO vo = IncidentVO.builder()
                .id(9L)
                .title("由告警创建")
                .status(IncidentStatus.OPEN)
                .source(IncidentSource.ALERT)
                .build();
        when(incidentService.createFromAlert(eq(7L), any())).thenReturn(vo);

        mockMvc.perform(post("/api/incidents/from-alert/7?actorId=10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.id").value(9))
                .andExpect(jsonPath("$.data.source").value("ALERT"));
    }

    @Test
    void scanSlaShouldReturnRecordedCount() throws Exception {
        when(incidentService.scanSlaBreaches(100)).thenReturn(2);

        mockMvc.perform(post("/api/incidents/sla/scan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data").value(2));
    }
}
