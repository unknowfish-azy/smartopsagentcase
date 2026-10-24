package com.smartops.dto.model;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import lombok.Data;

@Data
public class ModelConnectionUpdateRequest {

    private String name;

    private String provider;

    private String baseUrl;

    private String modelName;

    /**
     * 为空：
     * 保留原 API Key。
     */
    private String apiKey;

    private Boolean enabled;

    @Min(5)
    @Max(300)
    private Integer timeoutSeconds;
}