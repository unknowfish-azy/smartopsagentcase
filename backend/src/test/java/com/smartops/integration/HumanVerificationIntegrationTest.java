package com.smartops.integration;

import com.smartops.service.ModelConnectionService;
import com.smartops.security.HumanVerificationProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import java.time.Instant;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.anyString;

@SpringBootTest(properties = {
        "smartops.security.human-verification.enabled=true",
        "smartops.security.human-verification.site-key=site-for-isolated-test",
        "smartops.security.human-verification.secret-key=secret-for-isolated-test",
        "smartops.security.human-verification.hostnames=ops.example.test"
})
@AutoConfigureMockMvc
@ActiveProfiles("test")
class HumanVerificationIntegrationTest {
    @Autowired MockMvc mvc;
    @MockBean ModelConnectionService connections;
    @MockBean HumanVerificationProvider provider;

    @Test
    void registrationCannotBypassVerificationByCallingApiDirectly() throws Exception {
        mvc.perform(securedPost("/api/auth/register").contentType("application/json")
                .content("{\"username\":\"humancheck\",\"password\":\"LongPassword123!\",\"confirmPassword\":\"LongPassword123!\"}"))
                .andExpect(status().is(428));
    }

    @Test
    void administratorRequiresVerificationBeforePasswordCheck() throws Exception {
        mvc.perform(securedPost("/api/auth/login").contentType("application/json")
                .content("{\"username\":\"admin\",\"password\":\"invalid-password\",\"portal\":\"admin\"}"))
                .andExpect(status().is(428));
    }

    @Test
    void verificationDoesNotReplaceCsrf() throws Exception {
        mvc.perform(post("/api/auth/register").contentType("application/json")
                .content("{\"username\":\"humancheck\",\"password\":\"LongPassword123!\",\"confirmPassword\":\"LongPassword123!\",\"humanToken\":\"forged\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void publicPolicyDoesNotExposeSecretAndIsNotCacheable() throws Exception {
        mvc.perform(get("/api/auth/human-verification").param("action", "register"))
                .andExpect(status().isOk()).andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.data.required").value(true))
                .andExpect(jsonPath("$.data.secretKey").doesNotExist());
    }

    @Test
    void validVerificationAllowsPasswordCheckButCannotBeReplayed() throws Exception {
        var sessionResult = mvc.perform(get("/api/auth/session")).andReturn();
        var session = (MockHttpSession) sessionResult.getRequest().getSession(false);
        var mapper = new ObjectMapper();
        String csrf = mapper.readTree(sessionResult.getResponse().getContentAsString()).path("data").path("csrfToken").asText();
        var policyResult = mvc.perform(get("/api/auth/human-verification").session(session).param("action", "admin_login"))
                .andExpect(status().isOk()).andReturn();
        String challenge = mapper.readTree(policyResult.getResponse().getContentAsString()).path("data").path("challenge").asText();
        when(provider.verify("integration-token")).thenReturn(new HumanVerificationProvider.Result(true, "ops.example.test", "admin_login", challenge, Instant.now()));
        String body = "{\"username\":\"nonexistent\",\"password\":\"invalid-password\",\"portal\":\"admin\",\"humanToken\":\"integration-token\"}";
        mvc.perform(post("/api/auth/login").session(session).header("X-CSRF-TOKEN", csrf).contentType("application/json").content(body))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/auth/login").session(session).header("X-CSRF-TOKEN", csrf).contentType("application/json").content(body))
                .andExpect(status().is(428));
        verify(provider, times(1)).verify(anyString());
    }

    private MockHttpServletRequestBuilder securedPost(String path) throws Exception {
        var result = mvc.perform(get("/api/auth/session")).andReturn();
        String csrf = new ObjectMapper().readTree(result.getResponse().getContentAsString()).path("data").path("csrfToken").asText();
        return post(path).session((MockHttpSession) result.getRequest().getSession(false)).header("X-CSRF-TOKEN", csrf);
    }
}
