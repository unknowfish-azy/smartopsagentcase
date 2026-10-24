package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.net.SocketTimeoutException;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class TurnstileVerificationProviderTest {
    @Test
    void postsSecretToFixedEndpointAndParsesBoundResult() {
        var builder = RestClient.builder();
        var server = MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo(TurnstileVerificationProvider.ENDPOINT))
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_FORM_URLENCODED))
                .andExpect(content().string("secret=secret&response=token"))
                .andRespond(withSuccess("{\"success\":true,\"hostname\":\"ops.example.test\",\"action\":\"register\",\"cdata\":\"nonce\",\"challenge_ts\":\"2026-10-03T00:00:00Z\"}", MediaType.APPLICATION_JSON));
        var result = provider(builder).verify("token");
        assertTrue(result.success());
        assertEquals("register", result.action());
        assertEquals("nonce", result.cdata());
        server.verify();
    }

    @Test
    void malformedResponsesAndTransportErrorsFailClosedWithoutLeakingSecrets() {
        for (String scenario : new String[] { "malformed", "timeout", "http", "missing-time" }) {
            var builder = RestClient.builder();
            var server = MockRestServiceServer.bindTo(builder).build();
            var expectation = server.expect(requestTo(TurnstileVerificationProvider.ENDPOINT));
            if (scenario.equals("timeout")) expectation.andRespond(withException(new SocketTimeoutException("secret")));
            else if (scenario.equals("http")) expectation.andRespond(withServerError());
            else expectation.andRespond(withSuccess(scenario.equals("malformed") ? "{}" : "{\"success\":true}", MediaType.APPLICATION_JSON));
            var failure = assertThrows(BusinessException.class, () -> provider(builder).verify("token"));
            assertEquals(503, failure.getCode());
            assertFalse(failure.getMessage().contains("secret"));
            server.verify();
        }
    }

    @Test
    void invalidAndReusedTokensRemainRejected() {
        var builder = RestClient.builder();
        var server = MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo(TurnstileVerificationProvider.ENDPOINT))
                .andRespond(withSuccess("{\"success\":false,\"error-codes\":[\"timeout-or-duplicate\"]}", MediaType.APPLICATION_JSON));
        assertFalse(provider(builder).verify("replayed-token").success());
        server.verify();
    }

    private TurnstileVerificationProvider provider(RestClient.Builder builder) {
        return new TurnstileVerificationProvider(new HumanVerificationSettings(true, "site", "secret", "ops.example.test", 600, true, new MockEnvironment()), builder.build());
    }
}
