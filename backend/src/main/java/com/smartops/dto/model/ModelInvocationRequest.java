package com.smartops.dto.model;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class ModelInvocationRequest {

    @NotBlank
    private String prompt;
    private String systemPrompt;

    @DecimalMin("0.0")
    @DecimalMax("2.0")
    private Double temperature = 0.2;
}
