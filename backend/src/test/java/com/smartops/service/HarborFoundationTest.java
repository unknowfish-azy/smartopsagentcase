package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class HarborFoundationTest {
    private HarborCatalogService service(String url) {
        var recorder = mock(OperationRunRecorder.class);
        when(recorder.start(anyString(), anyLong(), any(), anyString(), any()))
                .thenReturn(new OperationRunRecorder.RunHandle(3L, "trace"));
        return new HarborCatalogService(new ObjectMapper(), recorder, url, "reader", "secret-value");
    }

    @Test void configuration_is_not_connectivity() {
        var result = service("").checkConnection(1L);
        assertThat(result.state()).isEqualTo("UNCONFIGURED");
        assertThat(result.checkedAt()).isNotNull();
        assertThat(result.traceId()).isNull();
    }

    @Test void reads_nested_repository_artifacts_and_preserves_evidence_fields() throws Exception {
        var path = new AtomicReference<String>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            path.set(exchange.getRequestURI().toASCIIString());
            byte[] bytes = "[{\"digest\":\"sha256:abc\",\"size\":123,\"type\":\"IMAGE\",\"push_time\":\"2026-10-02T10:00:00Z\",\"tags\":[{\"name\":\"v1\"}],\"extra_attrs\":{\"os\":\"linux\",\"architecture\":\"amd64\"}}]".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (var output = exchange.getResponseBody()) { output.write(bytes); }
        });
        server.start();
        try {
            var result = service("http://127.0.0.1:" + server.getAddress().getPort()).listArtifacts(1L, "demo", "team/image", 2);
            assertThat(path.get()).contains("/projects/demo/repositories/team%252Fimage/artifacts?page=2&page_size=20");
            assertThat(result.items()).hasSize(1);
            assertThat(result.items().get(0).digest()).isEqualTo("sha256:abc");
            assertThat(result.items().get(0).tags()).containsExactly("v1");
            assertThat(result.items().get(0).platforms()).containsExactly("linux/amd64");
            assertThat(result.items().get(0).size()).isEqualTo(123L);
        } finally { server.stop(0); }
    }

    @Test void rejects_path_injection_before_contacting_upstream() {
        var service = service("http://127.0.0.1:1");
        for (String repository : new String[]{"../image", "a/../b", "/image", "a%2fb", "a?x=y", "a//b", "https://evil"}) {
            assertThatThrownBy(() -> service.listArtifacts(1L, "demo", repository, 1)).isInstanceOf(BusinessException.class);
        }
    }

    @Test void connection_checks_classify_failures_without_exposing_upstream_body() throws Exception {
        var status = new java.util.concurrent.atomic.AtomicInteger(401);
        var body = new AtomicReference<>("secret-value internal-host");
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            byte[] bytes = body.get().getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status.get(), bytes.length);
            try (var output = exchange.getResponseBody()) { output.write(bytes); }
        });
        server.start();
        try {
            var service = service("http://127.0.0.1:" + server.getAddress().getPort());
            for (var entry : java.util.Map.of(401, "AUTHENTICATION", 403, "AUTHORIZATION", 302, "UPSTREAM", 429, "RATE_LIMIT").entrySet()) {
                status.set(entry.getKey());
                var check = service.checkConnection(1L);
                assertThat(check.state()).isEqualTo(entry.getValue());
                assertThat(check.traceId()).isNotBlank();
                assertThat(new ObjectMapper().findAndRegisterModules().writeValueAsString(check)).doesNotContain("secret-value", "internal-host");
            }
            status.set(200);
            assertThat(service.checkConnection(1L).state()).isEqualTo("INVALID_RESPONSE");
            body.set("[null]");
            assertThat(service.checkConnection(1L).state()).isEqualTo("INVALID_RESPONSE");
            body.set("[]");
            assertThat(service.checkConnection(1L).state()).isEqualTo("READABLE");
        } finally { server.stop(0); }
    }
}
