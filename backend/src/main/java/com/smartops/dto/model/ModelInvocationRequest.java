package com.smartops.dto.model;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
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

    /**
     * 输出 token 上限。为空时不传该字段，由供应商使用默认值；
     * 部分网关按"输入 + 最大输出"预留 TPM 配额，长默认输出会被判 429，
     * 因此短回答场景应显式设置。
     */
    @Min(1)
    @Max(8192)
    private Integer maxTokens;
}
