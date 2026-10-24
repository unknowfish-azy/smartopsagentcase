package com.smartops.service;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class IncidentRecommendationServiceTest {
    @Test
    void recommendsMatchingMemoryWithEvidenceAndRiskBoundary() {
        var service = new IncidentRecommendationService();
        var result = service.recommend(new IncidentRecommendationService.IncidentPattern("nginx", "502 upstream timeout", "HIGH", List.of("upstream timeout")), List.of(
                new OperatorMemoryService.Memory(1L, 1L, "nginx:502", "TOOL", "先查 upstream 状态", "trace-1", 3, 0.8, "ACTIVE", null, null)));
        assertThat(result).hasSize(1);
        assertThat(result.get(0).source()).isEqualTo("OPERATOR_MEMORY");
        assertThat(result.get(0).risk()).isEqualTo("HIGH");
        assertThat(result.get(0).verification()).isNotBlank();
    }
}
