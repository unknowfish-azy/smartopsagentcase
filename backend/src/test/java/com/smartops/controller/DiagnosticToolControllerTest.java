package com.smartops.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.diagnostics.HealthDiagnosticService;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DiagnosticToolControllerTest {
    private HealthDiagnosticService service;
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        service = mock(HealthDiagnosticService.class);
        mvc = MockMvcBuilders.standaloneSetup(new HealthDiagnosticController(service)).build();
    }

    @Test
    void healthEndpointPassesTheAuthenticatedUserToTheService() throws Exception {
        var summary = new HealthDiagnosticService.Summary("user", List.of(
                new HealthDiagnosticService.Check("session", "服务端会话", "HEALTHY", "user", "LOCAL_CHECK", "2026-10-02T00:00:00Z", 0, "ok", "无需处理")));
        when(service.summary(any())).thenReturn(summary);

        mvc.perform(get("/api/diagnostics/health")
                        .principal(new SessionUser(11L, "operator", "operator", "user", false, 0)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.scope").value("user"))
                .andExpect(jsonPath("$.data.checks[0].status").value("HEALTHY"));

        verify(service).summary(any(SessionUser.class));
    }

    @Test
    void adminHealthEndpointUsesTheAdminServicePath() throws Exception {
        when(service.adminSummary(any())).thenReturn(new HealthDiagnosticService.Summary("admin", List.of()));

        mvc.perform(get("/api/diagnostics/admin/health")
                        .principal(new SessionUser(1L, "admin", "admin", "admin", false, 0)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.scope").value("admin"));

        verify(service).adminSummary(any(SessionUser.class));
    }
}
