package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class ObservabilityServiceTest {
    private OperationRunRecorder recorder() {
        var r = mock(OperationRunRecorder.class);
        when(r.start(anyString(), anyLong(), any(), anyString(), any()))
                .thenReturn(new OperationRunRecorder.RunHandle(9L, "trace"));
        return r;
    }

    @Test void unconfigured_and_invalid_inputs_do_not_make_requests() {
        var r = recorder();
        var s = new ObservabilityService(new ObjectMapper(), r, "", "", "", "");
        assertThat(s.sources()).allMatch(x -> !x.configured());
        assertThatThrownBy(() -> s.query(1L, "prometheus", "up", 15, 200)).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> s.query(1L, "loki", "{}", 61, 200)).isInstanceOf(BusinessException.class);
        verify(r, never()).start(anyString(), anyLong(), any(), anyString(), any());
    }

    @Test void encodes_expressions_and_audits_without_tokens_or_raw_queries() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        var request = new AtomicReference<String>();
        var auth = new AtomicReference<String>();
        server.createContext("/", exchange -> {
            request.set(exchange.getRequestURI().toString());
            auth.set(exchange.getRequestHeaders().getFirst("Authorization"));
            byte[] bytes = "{\"status\":\"success\",\"data\":{\"resultType\":\"streams\",\"result\":[]}}".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (var out = exchange.getResponseBody()) { out.write(bytes); }
        });
        server.start();
        try {
            String url = "http://127.0.0.1:" + server.getAddress().getPort();
            var r = recorder();
            var s = new ObservabilityService(new ObjectMapper(), r, url, "private-token", url, "private-token");
            for (String source : java.util.List.of("prometheus", "loki")) {
                var result = s.query(1L, source, "{app=\"中文&api\"}", 15, 20);
                assertThat(result.traceId()).isNotBlank();
                assertThat(result.response().path("data").path("result").size()).isZero();
                assertThat(request.get()).contains("query_range", "start=", "end=");
                assertThat(URLDecoder.decode(request.get(), StandardCharsets.UTF_8)).contains("中文&api");
                assertThat(auth.get()).isEqualTo("Bearer private-token");
            }
            verify(r, times(2)).finish(any(), eq("SUCCEEDED"), any());
            verify(r, times(2)).recordCommand(any(), eq(1), argThat(x -> !x.contains("中文") && !x.contains("private-token")),
                    eq(0), anyString(), eq(""), any(), any());
        } finally { server.stop(0); }
    }

    @Test void errors_redirects_and_oversized_results_fail_and_are_audited() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        var mode = new java.util.concurrent.atomic.AtomicInteger(401);
        server.createContext("/", exchange -> {
            int status = mode.get();
            byte[] bytes = status == 200 ? new byte[1_048_577] : "private-error".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Location", "http://untrusted.invalid");
            exchange.sendResponseHeaders(status, bytes.length);
            try (var out = exchange.getResponseBody()) { out.write(bytes); }
        });
        server.start();
        try {
            var r = recorder();
            var s = new ObservabilityService(new ObjectMapper(), r,
                    "http://127.0.0.1:" + server.getAddress().getPort(), "", "", "");
            for (int status : new int[]{401, 302, 200}) {
                mode.set(status);
                assertThatThrownBy(() -> s.query(1L, "prometheus", "up", 15, 200))
                        .isInstanceOf(BusinessException.class).hasMessageNotContaining("private-error");
            }
            verify(r, times(3)).finish(any(), eq("FAILED"), any());
        } finally { server.stop(0); }
    }
}
