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

class HarborCatalogServiceTest {
    private OperationRunRecorder recorder() {
        var recorder = mock(OperationRunRecorder.class);
        when(recorder.start(anyString(), anyLong(), any(), anyString(), any()))
                .thenReturn(new OperationRunRecorder.RunHandle(3L, "trace"));
        return recorder;
    }

    @Test void unconfigured_source_and_invalid_project_do_not_make_requests() {
        var recorder = recorder();
        var service = new HarborCatalogService(new ObjectMapper(), recorder, "", "", "");
        assertThat(service.status().configured()).isFalse();
        assertThatThrownBy(() -> service.listProjects(1L, 1)).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.listRepositories(1L, "../admin", 1)).isInstanceOf(BusinessException.class);
        verify(recorder, never()).start(anyString(), anyLong(), any(), anyString(), any());
    }

    @Test void lists_real_projects_and_repositories_with_backend_only_basic_auth_and_audit() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        var path = new AtomicReference<String>();
        var auth = new AtomicReference<String>();
        server.createContext("/api/v2.0/", exchange -> {
            path.set(exchange.getRequestURI().toString());
            auth.set(exchange.getRequestHeaders().getFirst("Authorization"));
            byte[] body = (path.get().contains("repositories")
                    ? "[{\"name\":\"demo/nginx\",\"artifact_count\":2}]"
                    : "[{\"name\":\"demo\",\"metadata\":{\"public\":\"false\"},\"repo_count\":1}]")
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("X-Total-Count", "1");
            exchange.sendResponseHeaders(200, body.length);
            try (var out = exchange.getResponseBody()) { out.write(body); }
        });
        server.start();
        try {
            var recorder = recorder();
            var service = new HarborCatalogService(new ObjectMapper(), recorder,
                    "http://127.0.0.1:" + server.getAddress().getPort(), "robot$smartops", "private-secret");
            assertThat(service.status().credentialsConfigured()).isTrue();
            var projects = service.listProjects(1L, 2);
            assertThat(path.get()).contains("/api/v2.0/projects?page=2&page_size=20");
            assertThat(projects.items()).hasSize(1);
            assertThat(projects.items().get(0).name()).isEqualTo("demo");
            assertThat(projects.items().get(0).publicAccess()).isFalse();
            var repositories = service.listRepositories(1L, "demo", 1);
            assertThat(path.get()).contains("/api/v2.0/projects/demo/repositories?page=1&page_size=20");
            assertThat(repositories.items().get(0).name()).isEqualTo("demo/nginx");
            assertThat(repositories.items().get(0).artifactCount()).isEqualTo(2);
            assertThat(auth.get()).startsWith("Basic ").doesNotContain("private-secret");
            verify(recorder, times(2)).finish(any(), eq("SUCCEEDED"), any());
            verify(recorder, times(2)).recordCommand(any(), eq(1), argThat(x -> !x.contains("private-secret")),
                    eq(0), anyString(), eq(""), any(), any());
        } finally { server.stop(0); }
    }

    @Test void rejects_upstream_errors_redirects_and_private_response_bodies() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            exchange.getResponseHeaders().set("Location", "http://untrusted.invalid");
            byte[] body = "secret upstream detail".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(302, body.length);
            try (var out = exchange.getResponseBody()) { out.write(body); }
        });
        server.start();
        try {
            var recorder = recorder();
            var service = new HarborCatalogService(new ObjectMapper(), recorder,
                    "http://127.0.0.1:" + server.getAddress().getPort(), "", "");
            assertThatThrownBy(() -> service.listProjects(1L, 1))
                    .isInstanceOf(BusinessException.class).hasMessageNotContaining("secret upstream detail");
            verify(recorder).finish(any(), eq("FAILED"), any());
        } finally { server.stop(0); }
    }
}
