package com.smartops.dto.model;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class ModelConnectionResponse {

    private Long id;

    private Long userId;

    private String name;

    private String provider;

    private String baseUrl;

    private String modelName;

    /**
     * 不返回 API Key。
     */
    private String apiKeyMasked;

    private Boolean enabled;

    private Integer timeoutSeconds;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}