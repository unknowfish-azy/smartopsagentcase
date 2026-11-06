package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.entity.ModelConnection;
import com.smartops.exception.BusinessException;
import com.smartops.security.PinnedDns;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ModelProviderClientTest {

    private static final String HOST = "127.0.0.1";

    private HttpServer server;
    private final AtomicInteger hits = new AtomicInteger();

    @AfterEach
    void stopServer() {
        PinnedDns.clear(HOST);
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void invokesProviderWithoutReturningCredential() throws Exception {
        server = HttpServer.create(new InetSocketAddress(HOST, 0), 0);
        server.createContext("/v1/chat/completions", exchange -> {
            hits.incrementAndGet();
            assertThat(exchange.getRequestHeaders().getFirst("Authorization"))
                    .isEqualTo("Bearer secret-for-test-only");
            String response = "{\"choices\":[{\"message\":{\"content\":\"healthy\"}}],"
                    + "\"usage\":{\"total_tokens\":4}}";
            byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();

        ModelConnection connection = new ModelConnection();
        connection.setId(1L);
        connection.setProvider("openai-compatible");
        connection.setModelName("ops-model");
        connection.setTimeoutSeconds(5);
        connection.setBaseUrl("http://" + HOST + ":" + server.getAddress().getPort() + "/v1");
        ModelInvocationRequest request = new ModelInvocationRequest();
        request.setPrompt("status");

        // 连接期 pin：生产路径由 ModelConnectionService 在出站前登记校验过的地址。
        PinnedDns.pin(HOST, List.of(InetAddress.getByName(HOST)));

        ModelInvocationResponse response = new ModelProviderClient(new ObjectMapper())
                .invoke(connection, "secret-for-test-only", request);

        assertThat(hits.get()).isEqualTo(1);
        assertThat(response.getContent()).isEqualTo("healthy");
        assertThat(response.getUsage()).containsEntry("total_tokens", 4);
        assertThat(new ObjectMapper().writeValueAsString(response))
                .doesNotContain("secret-for-test-only");
    }

    @Test
    void unpinnedHostFailsClosedWithoutConnecting() {
        ModelConnection connection = new ModelConnection();
        connection.setId(1L);
        connection.setProvider("openai-compatible");
        connection.setModelName("ops-model");
        connection.setTimeoutSeconds(5);
        connection.setBaseUrl("http://" + HOST + ":18080/v1");
        ModelInvocationRequest request = new ModelInvocationRequest();
        request.setPrompt("status");

        assertThatThrownBy(() -> new ModelProviderClient(new ObjectMapper())
                .invoke(connection, "secret-for-test-only", request))
                .isInstanceOfSatisfying(BusinessException.class,
                        error -> assertThat(error.getCode()).isEqualTo(502));
        assertThat(hits.get()).isZero();
    }
}
