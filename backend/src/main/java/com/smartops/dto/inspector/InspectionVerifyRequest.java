package com.smartops.dto.inspector;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.util.LinkedHashMap;
import java.util.Map;

@Data
public class InspectionVerifyRequest {

    @NotBlank
    private String inspectionId;
    private Boolean resolved;
    private String status;
    private Map<String, Object> details = new LinkedHashMap<>();
}
