package com.smartops.dto.inspector;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class InspectionReplanRequest {

    @NotBlank
    private String inspectionId;
    private String reason;
}
