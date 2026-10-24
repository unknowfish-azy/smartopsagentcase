package com.smartops.dto.inspector;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Data
public class InspectionRecordRequest {

    private String inspectionId;

    @NotBlank
    private String taskId;

    private String target = "AGENT";

    @NotBlank
    private String status;

    @NotBlank
    private String severity;

    private String category;
    private String agentClaim;

    @NotBlank
    private String reason;

    private String recommendation;
    private Boolean requiresHuman = false;

    @Valid
    private List<Issue> issues = new ArrayList<>();

    @Valid
    private List<Evidence> evidence = new ArrayList<>();

    private Verification verification;
    private Map<String, Object> metadata = new LinkedHashMap<>();

    @Data
    public static class Issue {
        @NotBlank
        private String category;
        @NotBlank
        private String severity;
        @NotBlank
        private String reason;
        private String recommendation;
    }

    @Data
    public static class Evidence {
        @NotBlank
        private String content;
        private String source;
        private String version = "latest";
        private Double score = 0.0;
    }

    @Data
    public static class Verification {
        private Boolean resolved;
        private String status;
        private Map<String, Object> details = new LinkedHashMap<>();
    }
}
