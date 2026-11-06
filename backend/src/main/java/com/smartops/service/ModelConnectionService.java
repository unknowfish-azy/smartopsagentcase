package com.smartops.service;

import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.dto.model.ModelConnectionCreateRequest;
import com.smartops.dto.model.ModelConnectionResponse;
import com.smartops.dto.model.ModelConnectionUpdateRequest;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.dto.model.RuntimeModelConnectionResponse;
import com.smartops.entity.ModelConnection;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.ModelConnectionMapper;
import com.smartops.security.OutboundUrlPolicy;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.util.List;

@Service
@RequiredArgsConstructor
public class ModelConnectionService {

    private final ModelConnectionMapper mapper;

    private final AesGcmCryptoService cryptoService;

    private final ModelProviderClient providerClient;
    private final ModelAnalyticsService analytics;


    @Transactional
    public ModelConnectionResponse create(
            Long userId,
            ModelConnectionCreateRequest request
    ) {

        ModelConnection entity =
                new ModelConnection();

        entity.setUserId(userId);
        entity.setName(
                request.getName().trim()
        );
        entity.setProvider(
                request.getProvider().trim()
        );
        entity.setBaseUrl(
                normalizeBaseUrl(
                        request.getBaseUrl()
                )
        );
        entity.setModelName(
                request.getModelName().trim()
        );

        String apiKey =
                request.getApiKey().trim();

        entity.setApiKeyCiphertext(
                cryptoService.encrypt(
                        apiKey
                )
        );

        entity.setApiKeyLast4(
                maskLast4(apiKey)
        );

        entity.setEnabled(
                request.getEnabled() == null
                        || request.getEnabled()
        );

        entity.setTimeoutSeconds(
                request.getTimeoutSeconds() == null
                        ? 60
                        : request.getTimeoutSeconds()
        );

        mapper.insert(entity);

        return toResponse(entity);
    }


    @Transactional
    public ModelConnectionResponse update(
            Long userId,
            Long id,
            ModelConnectionUpdateRequest request
    ) {

        ModelConnection existing =
                mapper.findById(
                        id,
                        userId
                );

        if (existing == null) {
            throw new IllegalArgumentException(
                    "模型连接不存在"
            );
        }

        ModelConnection entity =
                new ModelConnection();

        entity.setId(id);
        entity.setUserId(userId);

        entity.setName(
                trimOrNull(
                        request.getName()
                )
        );

        entity.setProvider(
                trimOrNull(
                        request.getProvider()
                )
        );

        if (request.getBaseUrl() != null) {
            entity.setBaseUrl(
                    normalizeBaseUrl(
                            request.getBaseUrl()
                    )
            );
        }

        entity.setModelName(
                trimOrNull(
                        request.getModelName()
                )
        );

        if (request.getApiKey() != null
                && !request.getApiKey().isBlank()) {

            String apiKey =
                    request.getApiKey().trim();

            entity.setApiKeyCiphertext(
                    cryptoService.encrypt(
                            apiKey
                    )
            );

            entity.setApiKeyLast4(
                    maskLast4(apiKey)
            );
        }

        entity.setEnabled(
                request.getEnabled()
        );

        entity.setTimeoutSeconds(
                request.getTimeoutSeconds()
        );

        mapper.update(entity);

        ModelConnection latest =
                mapper.findById(
                        id,
                        userId
                );

        return toResponse(latest);
    }


    public List<ModelConnectionResponse> list(
            Long userId
    ) {

        return mapper.findByUserId(
                        userId
                )
                .stream()
                .map(this::toResponse)
                .toList();
    }


    @Transactional
    public void delete(
            Long userId,
            Long id
    ) {

        mapper.deleteById(
                id,
                userId
        );
    }


    /**
     * 仅供内部 AI Runtime 使用。
     *
     * 不暴露给普通前端 API。
     */
    public RuntimeModelConnectionResponse getRuntimeConfiguration(
            Long userId,
            Long id
    ) {

        ModelConnection connection =
                mapper.findById(
                        id,
                        userId
                );

        if (connection == null) {
            throw new IllegalArgumentException(
                    "模型连接不存在"
            );
        }

        if (!Boolean.TRUE.equals(
                connection.getEnabled()
        )) {
            throw new IllegalStateException(
                    "模型连接已禁用"
            );
        }

        assertOutboundTarget(
                connection.getBaseUrl()
        );

        return RuntimeModelConnectionResponse.builder()
                .provider(connection.getProvider())
                .baseUrl(connection.getBaseUrl())
                .modelName(connection.getModelName())
                .enabled(connection.getEnabled())
                .timeoutSeconds(connection.getTimeoutSeconds())
                .keyLast4(connection.getApiKeyLast4())
                .build();
    }

    public ModelInvocationResponse invoke(
            Long userId,
            Long id,
            ModelInvocationRequest request
    ) {
        ModelConnection connection = mapper.findById(id, userId);
        if (connection == null) {
            throw new BusinessException(404, "模型连接不存在");
        }
        if (!Boolean.TRUE.equals(connection.getEnabled())) {
            throw new IllegalStateException("模型连接已禁用");
        }
        // 存量行可能在整改前写入内网地址；出站前按当前 DNS 重新校验一次（SEC-14）。
        assertOutboundTarget(connection.getBaseUrl());
        String apiKey = cryptoService.decrypt(connection.getApiKeyCiphertext());
        // Start the ledger before sending a billable request. Store neither prompts nor secrets.
        String invocationId = analytics.start(userId, id, connection.getModelName());
        long started = System.nanoTime();
        ModelInvocationResponse response;
        try {
            response = providerClient.invoke(connection, apiKey, request);
        } catch (RuntimeException ex) {
            try { analytics.finish(invocationId, false, (System.nanoTime() - started) / 1_000_000, java.util.Map.of()); }
            catch (RuntimeException recordingError) { ex.addSuppressed(recordingError); }
            throw ex;
        }
        // A logging outage must not turn a successful paid call into a retryable failure.
        try {
            analytics.finish(invocationId, response.getContent() != null && !response.getContent().isBlank(),
                    (System.nanoTime() - started) / 1_000_000, response.getUsage());
        } catch (RuntimeException recordingError) {
            org.slf4j.LoggerFactory.getLogger(ModelConnectionService.class)
                    .warn("Model usage finalization failed; invocation remains pending: {}", invocationId);
        }
        return response;
    }


    private ModelConnectionResponse toResponse(
            ModelConnection entity
    ) {

        return ModelConnectionResponse.builder()

                .id(entity.getId())

                .userId(entity.getUserId())

                .name(entity.getName())

                .provider(entity.getProvider())

                .baseUrl(entity.getBaseUrl())

                .modelName(entity.getModelName())

                .apiKeyMasked(
                        "****"
                                + (
                                entity.getApiKeyLast4()
                                        == null
                                        ? ""
                                        : entity.getApiKeyLast4()
                        )
                )

                .enabled(entity.getEnabled())

                .timeoutSeconds(
                        entity.getTimeoutSeconds()
                )

                .createdAt(
                        entity.getCreatedAt()
                )

                .updatedAt(
                        entity.getUpdatedAt()
                )

                .build();
    }


    private String normalizeBaseUrl(
            String url
    ) {

        String value =
                url.trim();

        while (
                value.endsWith("/")
        ) {
            value =
                    value.substring(
                            0,
                            value.length() - 1
                    );
        }

        assertOutboundTarget(value);

        return value;
    }


    /**
     * 模型连接的服务端出站目标校验（SEC-14）：与爬取共用同一套 IP 分类。
     *
     * <p>只允许 http/https 且解析后全部地址为公网地址；拒绝回环、私网、链路本地、
     * CGNAT、保留网段与无法解析的主机。错误信息只回显规则码，不回显目标主机。</p>
     */
    private void assertOutboundTarget(
            String baseUrl
    ) {

        if (baseUrl == null || baseUrl.isBlank()) {
            throw new BusinessException(
                    400,
                    "模型 Base URL 无效"
            );
        }

        URI uri;

        try {
            uri =
                    URI.create(
                            baseUrl.trim()
                    );
        } catch (IllegalArgumentException invalid) {
            throw new BusinessException(
                    400,
                    "模型 Base URL 无效"
            );
        }

        OutboundUrlPolicy.Decision decision =
                OutboundUrlPolicy.inspect(uri);

        if (!decision.allowed()) {
            throw new BusinessException(
                    400,
                    "模型 Base URL 被拒绝："
                            + decision.rule()
            );
        }
    }


    private String trimOrNull(
            String value
    ) {
        if (value == null) {
            return null;
        }

        String trimmed =
                value.trim();

        return trimmed.isEmpty()
                ? null
                : trimmed;
    }


    private String maskLast4(
            String value
    ) {

        if (value.length() <= 4) {
            return value;
        }

        return value.substring(
                value.length() - 4
        );
    }
}
