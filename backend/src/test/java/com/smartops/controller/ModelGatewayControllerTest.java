package com.smartops.controller;

import com.smartops.config.SecurityConfig;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.security.InternalTokenAuthenticationFilter;
import com.smartops.service.ModelGatewayService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ModelGatewayController.class)
@Import({SecurityConfig.class, InternalTokenAuthenticationFilter.class})
class ModelGatewayControllerTest {
    @Autowired MockMvc mvc;
    @MockBean ModelGatewayService gateway;
    @MockBean com.smartops.security.UserAccountService accounts;
    @MockBean com.smartops.security.SecurityAuditService audit;
    @MockBean com.smartops.security.AdminMfaService mfa;


    @Test void bearerKeyCanListModelsWithoutBrowserSession() throws Exception {
        var principal = new ModelGatewayService.GatewayPrincipal(1L, 2L, "PERSONAL");
        when(gateway.authenticate("sk-smartops-test")).thenReturn(principal);
        when(gateway.models(principal)).thenReturn(List.of(Map.of("id", "ops", "object", "model", "owned_by", "smartops")));
        mvc.perform(get("/v1/models").header("Authorization", "Bearer sk-smartops-test"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data[0].id").value("ops"));
    }

    @Test void chatUsesModelFieldAndOpenAiResponseShape() throws Exception {
        var principal = new ModelGatewayService.GatewayPrincipal(1L, 2L, "PERSONAL");
        when(gateway.authenticate("sk-smartops-test")).thenReturn(principal);
        when(gateway.invoke(eq(principal), eq("ops"), any())).thenReturn(ModelInvocationResponse.builder()
                .model("upstream-model").content("healthy").usage(Map.of("prompt_tokens", 3, "completion_tokens", 2, "total_tokens", 5)).build());
        mvc.perform(post("/v1/chat/completions").header("Authorization", "Bearer sk-smartops-test")
                        .contentType("application/json").content("{\"model\":\"ops\",\"messages\":[{\"role\":\"user\",\"content\":\"status\"}]}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.object").value("chat.completion"))
                .andExpect(jsonPath("$.model").value("ops"))
                .andExpect(jsonPath("$.choices[0].message.content").value("healthy"))
                .andExpect(jsonPath("$.usage.total_tokens").value(5))
                .andExpect(jsonPath("$.connectionId").doesNotExist());
    }

    @Test void streamingRequestUsesOpenAiSseChunks() throws Exception {
        var principal = new ModelGatewayService.GatewayPrincipal(1L, 2L, "PERSONAL");
        when(gateway.authenticate("sk-smartops-test")).thenReturn(principal);
        when(gateway.invoke(eq(principal), eq("ops"), any())).thenReturn(ModelInvocationResponse.builder()
                .model("upstream-model").content("healthy").usage(Map.of()).build());
        mvc.perform(post("/v1/chat/completions").header("Authorization", "Bearer sk-smartops-test")
                        .contentType("application/json").content("{\"model\":\"ops\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"status\"}]}"))
                .andExpect(status().isOk()).andExpect(result -> org.junit.jupiter.api.Assertions.assertTrue(result.getResponse().getContentType().startsWith("text/event-stream")))
                .andExpect(result -> org.junit.jupiter.api.Assertions.assertTrue(result.getResponse().getContentAsString().contains("chat.completion.chunk")))
                .andExpect(result -> org.junit.jupiter.api.Assertions.assertTrue(result.getResponse().getContentAsString().contains("data: [DONE]")));
    }

    @Test void missingBearerUsesOpenAiErrorShape() throws Exception {
        mvc.perform(get("/v1/models"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.type").value("authentication_error"));
    }
}
