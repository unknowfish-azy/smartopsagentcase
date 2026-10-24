package com.smartops.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.ServerCreateRequest;
import com.smartops.service.ServerService;
import com.smartops.vo.ServerVO;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

// 该测试聚焦 Controller 层逻辑，关闭安全过滤器，避免默认 Security 拦截。
@WebMvcTest(ServerController.class)
@AutoConfigureMockMvc(addFilters = false)
class ServerControllerTest {
    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private ServerService serverService;

    @Test
    void createServerShouldSuccess() throws Exception {

        ServerVO vo = ServerVO.builder()
                .id(1L)
                .name("Server-01")
                .host("127.0.0.1")
                .port(22)
                .os("Ubuntu 24.04")
                .build();

        when(serverService.create(any(ServerCreateRequest.class)))
                .thenReturn(vo);

        ServerCreateRequest request =
                new ServerCreateRequest();

        request.setName("Server-01");
        request.setHost("127.0.0.1");
        request.setPort(22);
        request.setOs("Ubuntu 24.04");

        mockMvc.perform(
                        post("/api/servers")
                                .contentType(APPLICATION_JSON)
                                .content(
                                        objectMapper.writeValueAsString(request)
                                )
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.id").value(1))
                .andExpect(jsonPath("$.data.name").value("Server-01"))
                .andExpect(jsonPath("$.data.host").value("127.0.0.1"));
    }

    @Test
    void createServerWithEmptyNameShouldReturn400()
            throws Exception {

        ServerCreateRequest request =
                new ServerCreateRequest();

        request.setName("");
        request.setHost("127.0.0.1");
        request.setPort(22);

        mockMvc.perform(
                        post("/api/servers")
                                .contentType(APPLICATION_JSON)
                                .content(
                                        objectMapper.writeValueAsString(request)
                                )
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(400));
    }
}
