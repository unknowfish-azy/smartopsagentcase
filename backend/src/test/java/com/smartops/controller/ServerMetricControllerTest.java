package com.smartops.controller;

import com.smartops.service.ServerMetricService;
import com.smartops.vo.ServerMetricVO;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.Mockito.when;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

// 该测试聚焦 Controller 层逻辑，关闭安全过滤器，避免默认 Security 拦截。
@WebMvcTest(ServerMetricController.class)
@AutoConfigureMockMvc(addFilters = false)
class ServerMetricControllerTest {
    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ServerMetricService metricService;

    @MockBean
    private com.smartops.service.ServerService serverService;

    @Test
    void getLatestMetricShouldSuccess()
            throws Exception {

        ServerMetricVO vo =
                ServerMetricVO.builder()
                        .id(1L)
                        .serverId(1L)
                        .cpuUsage(35.5)
                        .memoryUsage(52.2)
                        .diskUsage(61.3)
                        .build();

        when(metricService.latest(1L))
                .thenReturn(vo);

        var actor = new com.smartops.security.SessionUser(7L, "u7", "user", "user", false, 0);

        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(actor, null, List.of()));
        try {
            mockMvc.perform(
                            get("/api/servers/1/metrics/latest")
                    )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.serverId").value(1))
                    .andExpect(jsonPath("$.data.cpuUsage").value(35.5));
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
