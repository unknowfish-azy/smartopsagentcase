package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.entity.ModelConnection;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

class ModelProviderClientTest {

    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void invokesProviderWithoutReturningCredential() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/chat/completions", exchange -> {
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
        connection.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort() + "/v1");
        ModelInvocationRequest request = new ModelInvocationRequest();
        request.setPrompt("status");

        ModelInvocationResponse response = new ModelProviderClient(new ObjectMapper())
                .invoke(connection, "secret-for-test-only", request);

        assertThat(response.getContent()).isEqualTo("healthy");
        assertThat(response.getUsage()).containsEntry("total_tokens", 4);
        assertThat(new ObjectMapper().writeValueAsString(response))
                .doesNotContain("secret-for-test-only");
    }
}
