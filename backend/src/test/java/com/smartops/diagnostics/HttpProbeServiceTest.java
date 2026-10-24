package com.smartops.diagnostics;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class HttpProbeServiceTest {
    @Test void transportUsesPinnedAddressWithoutFollowingRedirectsAndBoundsBody() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        var landed = new AtomicInteger();
        server.createContext("/redirect", exchange -> {
            exchange.getResponseHeaders().add("Location", "http://127.0.0.1/forbidden?token=secret");
            exchange.sendResponseHeaders(302, -1); exchange.close();
        });
        server.createContext("/big", exchange -> {
            byte[] bytes = new byte[300000];
            exchange.sendResponseHeaders(200, bytes.length);
            try (var output = exchange.getResponseBody()) { output.write(bytes); } catch (Exception ignored) { }
        });
        server.createContext("/ok", exchange -> {
            landed.incrementAndGet();
            byte[] bytes = "{\"healthy\":true}".getBytes();
            exchange.sendResponseHeaders(200, bytes.length);
            try (var output = exchange.getResponseBody()) { output.write(bytes); }
        });
        server.start();
        try (var transport = new DiagnosticTransport()) {
            var result = transport.http(fixture(server, "/ok"), "GET");
            assertThat(new String(result.body())).contains("healthy");
            assertThat(landed).hasValue(1);
            assertThat(transport.http(fixture(server, "/redirect"), "GET").statusCode()).isEqualTo(302);
            assertThat(transport.http(fixture(server, "/big"), "GET").truncated()).isTrue();
            assertThat(transport.http(fixture(server, "/ok"), "HEAD").body()).isEmpty();
        } finally { server.stop(0); }
    }
    static DiagnosticTargetPolicy.ApprovedTarget fixture(HttpServer server, String path) throws Exception {
        return new DiagnosticTargetPolicy.ApprovedTarget("fixture", "fixture",
                URI.create("http://pinned.invalid:" + server.getAddress().getPort() + path),
                List.of(InetAddress.getByAddress("pinned.invalid", new byte[]{127,0,0,1})), List.of(11L), 200);
    }
    @Test void validatesAssertionsBeforeIoAndNeverReturnsRawBody() throws Exception {
        var transport = mock(DiagnosticTransport.class);
        var service = new HttpProbeService(DiagnosticTargetPolicyTest.policy("203.0.113.10"), new DiagnosticProbeLimiter(), transport, new ObjectMapper());
        var user = DiagnosticTargetPolicyTest.user(11);
        var json = new ObjectMapper();
        when(transport.http(any(), eq("GET"))).thenReturn(new DiagnosticTransport.HttpResult(200, "{\"ok\":true,\"secret\":\"hidden\"}".getBytes(), false));
        var success = service.check(user, new HttpProbeService.Request("web", "GET", "ok", "equals", json.readTree("true")));
        assertThat(success.status()).isEqualTo("HEALTHY");
        assertThat(success.assertion()).isEqualTo("PASS");
        assertThat(json.writeValueAsString(success)).doesNotContain("hidden");
        var fail = service.check(user, new HttpProbeService.Request("web", "GET", "missing", "exists", null));
        assertThat(fail.assertion()).isEqualTo("FAIL");
        clearInvocations(transport);
        assertThatThrownBy(() -> service.check(user, new HttpProbeService.Request("web", "POST", null, null, null))).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.check(user, new HttpProbeService.Request("web", "HEAD", "ok", "exists", null))).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.check(user, new HttpProbeService.Request("web", "GET", "ok", "unsupported", null))).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.check(user, new HttpProbeService.Request("web", "GET", "ok", "equals", null))).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.check(DiagnosticTargetPolicyTest.user(22), new HttpProbeService.Request("web", "GET", null, null, null))).isInstanceOf(BusinessException.class);
        verifyNoInteractions(transport);
    }
    @Test void truncatedAndInvalidJsonAreUnknownRatherThanPass() throws Exception {
        var transport = mock(DiagnosticTransport.class);
        var service = new HttpProbeService(DiagnosticTargetPolicyTest.policy("203.0.113.10"), new DiagnosticProbeLimiter(), transport, new ObjectMapper());
        when(transport.http(any(), any())).thenReturn(new DiagnosticTransport.HttpResult(200, "{}".getBytes(), true));
        assertThat(service.check(DiagnosticTargetPolicyTest.user(11), new HttpProbeService.Request("web", "GET", "ok", "exists", null)).assertion()).isEqualTo("UNKNOWN");
        when(transport.http(any(), any())).thenReturn(new DiagnosticTransport.HttpResult(200, "not json".getBytes(), false));
        assertThat(service.check(DiagnosticTargetPolicyTest.user(11), new HttpProbeService.Request("web", "GET", "ok", "exists", null)).assertion()).isEqualTo("UNKNOWN");
    }

    @Test
    void classifiesTimeoutNetworkAndAssertionFailuresWithoutRawDetails() throws Exception {
        var transport = mock(DiagnosticTransport.class);
        var service = new HttpProbeService(DiagnosticTargetPolicyTest.policy("203.0.113.10"), new DiagnosticProbeLimiter(), transport, new ObjectMapper());
        var user = DiagnosticTargetPolicyTest.user(11);
        when(transport.http(any(), eq("GET"))).thenThrow(new java.net.SocketTimeoutException("secret timeout"));
        assertThat(service.check(user, new HttpProbeService.Request("web", "GET", null, null, null)).errorCategory()).isEqualTo("TIMEOUT");
        when(transport.http(any(), eq("GET"))).thenThrow(new java.net.ConnectException("secret connection"));
        assertThat(service.check(user, new HttpProbeService.Request("web", "GET", null, null, null)).errorCategory()).isEqualTo("NETWORK");
        when(transport.http(any(), eq("GET"))).thenReturn(new DiagnosticTransport.HttpResult(500, "{\"status\":\"down\"}".getBytes(), false));
        var assertion = service.check(user, new HttpProbeService.Request("web", "GET", "status", "equals", new ObjectMapper().readTree("\"up\"")));
        assertThat(assertion.errorCategory()).isEqualTo("ASSERTION");
        assertThat(new ObjectMapper().writeValueAsString(assertion)).doesNotContain("secret");
    }

}
