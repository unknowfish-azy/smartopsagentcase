package com.smartops.dto.model;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class ModelConnectionCreateRequest {

    @NotBlank
    private String name;

    @NotBlank
    private String provider;

    @NotBlank
    private String baseUrl;

    @NotBlank
    private String modelName;

    @NotBlank
    private String apiKey;

    @NotNull
    private Boolean enabled = true;

    @Min(5)
    @Max(300)
    private Integer timeoutSeconds = 60;
}