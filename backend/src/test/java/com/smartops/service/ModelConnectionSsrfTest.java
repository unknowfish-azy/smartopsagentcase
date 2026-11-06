package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.dto.model.ModelConnectionCreateRequest;
import com.smartops.dto.model.ModelConnectionResponse;
import com.smartops.dto.model.ModelConnectionUpdateRequest;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.entity.ModelConnection;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.ModelConnectionMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * TM-32 / SEC-14：模型连接 baseUrl 内网 SSRF。
 *
 * <p>创建与更新必须拒绝私有/回环/元数据/非 http(s) 目标；存量恶意行在出站前也要被拦下，
 * 且 mock 供应商收到请求数为 0、连接行不落库。</p>
 */
class ModelConnectionSsrfTest {

    private final ModelConnectionMapper mapper = mock(ModelConnectionMapper.class);
    private final AesGcmCryptoService crypto = mock(AesGcmCryptoService.class);
    private final ModelAnalyticsService analytics = mock(ModelAnalyticsService.class);
    private final ModelProviderClient provider =
            new ModelProviderClient(new ObjectMapper());
    private final ModelConnectionService service =
            new ModelConnectionService(mapper, crypto, provider, analytics);

    private HttpServer server;
    private final AtomicInteger providerHits = new AtomicInteger();

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    private String localMockBaseUrl() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/chat/completions", exchange -> {
            providerHits.incrementAndGet();
            byte[] bytes = "{\"choices\":[{\"message\":{\"content\":\"should-not-arrive\"}}]}"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
        return "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
    }

    private ModelConnectionCreateRequest createRequest(String baseUrl) {
        ModelConnectionCreateRequest request = new ModelConnectionCreateRequest();
        request.setName("local-model");
        request.setProvider("openai-compatible");
        request.setBaseUrl(baseUrl);
        request.setModelName("ops-model");
        request.setApiKey("secret-for-test-only");
        return request;
    }

    @Test
    void privateLoopbackAndMetadataTargetsAreRejectedOnCreate() throws Exception {
        for (String baseUrl : new String[]{
                "http://127.0.0.1:18080/v1",
                "http://localhost:18080/v1/",
                "http://10.0.0.1/v1",
                "http://172.16.0.1/v1",
                "http://192.168.1.1/v1",
                "http://169.254.169.254/latest/meta-data",
                "http://[::1]:18080/v1",
                "http://[::ffff:127.0.0.1]:18080/v1",
                "ftp://8.8.8.8/v1",
                "file:///etc/passwd"
        }) {
            assertThatThrownBy(() -> service.create(7L, createRequest(baseUrl)))
                    .as(baseUrl)
                    .isInstanceOfSatisfying(BusinessException.class, error -> {
                        assertThat(error.getCode()).isEqualTo(400);
                        assertThat(error.getMessage()).doesNotContain("127.0.0.1", "169.254");
                    });
        }
        verify(mapper, never()).insert(any());
        verifyNoInteractions(crypto);
    }

    @Test
    void unreachableCreateSendsNoRequestToProvider() throws Exception {
        String baseUrl = localMockBaseUrl();

        assertThatThrownBy(() -> service.create(7L, createRequest(baseUrl)))
                .isInstanceOfSatisfying(BusinessException.class,
                        error -> assertThat(error.getCode()).isEqualTo(400));

        assertThat(providerHits.get()).isZero();
        verify(mapper, never()).insert(any());
    }

    @Test
    void publicTargetIsAcceptedAndNormalized() {
        when(crypto.encrypt("secret-for-test-only")).thenReturn("ciphertext");

        ModelConnectionResponse response =
                service.create(7L, createRequest("http://8.8.8.8/v1/"));

        assertThat(response.getBaseUrl()).isEqualTo("http://8.8.8.8/v1");
        verify(mapper).insert(any());
    }

    @Test
    void updateRejectsPrivateBaseUrlWithoutWriting() {
        ModelConnection existing = new ModelConnection();
        existing.setId(9L);
        existing.setEnabled(true);
        existing.setBaseUrl("https://model.example/v1");
        when(mapper.findById(9L, 7L)).thenReturn(existing);

        ModelConnectionUpdateRequest update = new ModelConnectionUpdateRequest();
        update.setBaseUrl("http://127.0.0.1:18080/");

        assertThatThrownBy(() -> service.update(7L, 9L, update))
                .isInstanceOfSatisfying(BusinessException.class,
                        error -> assertThat(error.getCode()).isEqualTo(400));
        verify(mapper, never()).update(any());
    }

    @Test
    void legacyPrivateRowIsBlockedBeforeAnyOutboundCall() throws Exception {
        String baseUrl = localMockBaseUrl();
        ModelConnection legacy = new ModelConnection();
        legacy.setId(8L);
        legacy.setUserId(7L);
        legacy.setEnabled(true);
        legacy.setModelName("ops-model");
        legacy.setApiKeyCiphertext("encrypted");
        legacy.setBaseUrl(baseUrl);
        when(mapper.findById(8L, 7L)).thenReturn(legacy);

        assertThatThrownBy(() -> service.invoke(7L, 8L, new ModelInvocationRequest()))
                .isInstanceOfSatisfying(BusinessException.class,
                        error -> assertThat(error.getCode()).isEqualTo(400));

        assertThat(providerHits.get()).isZero();
        verifyNoInteractions(analytics, crypto);
    }

    @Test
    void runtimeConfigurationRejectsLegacyPrivateRow() {
        ModelConnection legacy = new ModelConnection();
        legacy.setId(8L);
        legacy.setUserId(7L);
        legacy.setEnabled(true);
        legacy.setBaseUrl("http://169.254.169.254/v1");
        when(mapper.findById(8L, 7L)).thenReturn(legacy);

        assertThatThrownBy(() -> service.getRuntimeConfiguration(7L, 8L))
                .isInstanceOfSatisfying(BusinessException.class,
                        error -> assertThat(error.getCode()).isEqualTo(400));
    }
}
