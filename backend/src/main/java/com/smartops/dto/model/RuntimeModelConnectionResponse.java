package com.smartops.dto.model;

import lombok.Builder;
import lombok.Data;

/** Minimum non-secret model metadata exposed to an authenticated service. */
@Data
@Builder
public class RuntimeModelConnectionResponse {

    private String provider;
    private String baseUrl;
    private String modelName;
    private Boolean enabled;
    private Integer timeoutSeconds;
    private String keyLast4;
}
