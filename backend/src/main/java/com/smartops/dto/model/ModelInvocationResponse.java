package com.smartops.dto.model;

import lombok.Builder;
import lombok.Data;

import java.util.Map;

@Data
@Builder
public class ModelInvocationResponse {
    private Long connectionId;
    private String provider;
    private String model;
    private String content;
    private Map<String, Object> usage;
}
