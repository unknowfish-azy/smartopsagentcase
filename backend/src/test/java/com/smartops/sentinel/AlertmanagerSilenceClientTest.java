package com.smartops.sentinel;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-09：外部静默 API 必须是真实 HTTP 语义。
 *
 * <p>用本地 HttpServer 校验路径、方法与请求体；失败（5xx / 缺 silenceID）
 * 必须抛异常，不能被调用方记成"同步成功"。</p>
 */
class AlertmanagerSilenceClientTest {

    @Test
    void createPostsMatchersAndReturnsExternalId() throws Exception {
        AtomicReference<String> captured = new AtomicReference<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/v2/silences", exchange -> {
            captured.set(exchange.getRequestMethod() + "\n"
                    + exchange.getRequestHeaders().getFirst("Authorization") + "\n"
                    + new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] body = "{\"silenceID\":\"ext-77\"}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });
        server.start();
        try {
            AlertmanagerSilenceClient client = new AlertmanagerSilenceClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(), "secret");

            String id = client.create("TASK", 5101L,
                    java.time.Instant.parse("2026-11-06T01:00:00Z"),
                    java.time.Instant.parse("2026-11-06T05:00:00Z"),
                    "维护窗口", "91");

            assertThat(id).isEqualTo("ext-77");
            assertThat(captured.get()).contains("POST", "Bearer secret",
                    "\"smartops_task\"", "\"5101\"",
                    "2026-11-06T01:00:00Z", "2026-11-06T05:00:00Z",
                    "\"comment\":\"维护窗口\"");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void globalSilenceUsesRegexMatcher() throws Exception {
        AtomicReference<String> captured = new AtomicReference<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/v2/silences", exchange -> {
            captured.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] body = "{\"silenceID\":\"ext-1\"}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });
        server.start();
        try {
            AlertmanagerSilenceClient client = new AlertmanagerSilenceClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(), "");

            client.create("GLOBAL", null,
                    java.time.Instant.parse("2026-11-06T01:00:00Z"),
                    java.time.Instant.parse("2026-11-06T05:00:00Z"), "全局", "91");

            assertThat(captured.get()).contains("\"smartops_scope\"", "\".*\"", "\"isRegex\":true");
            assertThat(captured.get()).doesNotContain("smartops_task");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void missingSilenceIdIsFailureNotSuccess() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/v2/silences", exchange -> {
            byte[] body = "{}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });
        server.start();
        try {
            AlertmanagerSilenceClient client = new AlertmanagerSilenceClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(), "");

            assertThatThrownBy(() -> client.create("TASK", 5101L,
                    java.time.Instant.parse("2026-11-06T01:00:00Z"),
                    java.time.Instant.parse("2026-11-06T05:00:00Z"), "维护", "91"))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("silenceID");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void serverErrorOnCreatePropagates() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/v2/silences", exchange -> {
            exchange.sendResponseHeaders(500, -1);
            exchange.close();
        });
        server.start();
        try {
            AlertmanagerSilenceClient client = new AlertmanagerSilenceClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(), "");

            assertThatThrownBy(() -> client.create("GLOBAL", null,
                    java.time.Instant.parse("2026-11-06T01:00:00Z"),
                    java.time.Instant.parse("2026-11-06T05:00:00Z"), "全局", "91"))
                    .isInstanceOf(RuntimeException.class);
        } finally {
            server.stop(0);
        }
    }

    @Test
    void expireDeletesExternalSilenceAndPropagatesFailure() throws Exception {
        AtomicReference<String> method = new AtomicReference<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/v2/silence/ext-42", exchange -> {
            method.set(exchange.getRequestMethod());
            exchange.sendResponseHeaders(200, -1);
            exchange.close();
        });
        server.start();
        try {
            AlertmanagerSilenceClient client = new AlertmanagerSilenceClient(
                    "http://127.0.0.1:" + server.getAddress().getPort(), "");

            client.expire("ext-42");
            assertThat(method.get()).isEqualTo("DELETE");
        } finally {
            server.stop(0);
        }

        HttpServer failing = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        failing.createContext("/api/v2/silence/ext-42", exchange -> {
            exchange.sendResponseHeaders(500, -1);
            exchange.close();
        });
        failing.start();
        try {
            AlertmanagerSilenceClient client = new AlertmanagerSilenceClient(
                    "http://127.0.0.1:" + failing.getAddress().getPort(), "");

            assertThatThrownBy(() -> client.expire("ext-42"))
                    .isInstanceOf(RuntimeException.class);
        } finally {
            failing.stop(0);
        }
    }

    @Test
    void unconfiguredClientRefusesToPretendSuccess() {
        AlertmanagerSilenceClient client = new AlertmanagerSilenceClient("", "");

        assertThat(client.configured()).isFalse();
        assertThatThrownBy(() -> client.create("GLOBAL", null,
                java.time.Instant.parse("2026-11-06T01:00:00Z"),
                java.time.Instant.parse("2026-11-06T05:00:00Z"), "全局", "91"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("未配置");
        assertThatThrownBy(() -> client.expire("ext-1"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("未配置");
    }
}
