package com.smartops.service;

import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Locale;

@Service
public class IncidentRecommendationService {
    public List<Recommendation> recommend(IncidentPattern incident, List<OperatorMemoryService.Memory> memories) {
        String haystack = (incident.service() + " " + incident.symptom() + " " + String.join(" ", incident.evidence())).toLowerCase(Locale.ROOT);
        return memories.stream().filter(memory -> "ACTIVE".equals(memory.status()))
                .filter(memory -> matches(haystack, memory.incidentKey()))
                .map(memory -> new Recommendation(memory.preferredAction(), "OPERATOR_MEMORY", Math.min(0.99, memory.confidence()), incident.risk(), "执行前核对证据：" + String.join("、", incident.evidence()) + "；完成后验证服务健康状态。", memory.sourceRefs()))
                .toList();
    }

    private boolean matches(String haystack, String key) {
        if (key == null || key.isBlank()) return false;
        String normalized = key.toLowerCase(Locale.ROOT).replace(':', ' ');
        return normalized.isBlank() || haystack.contains(normalized) || normalized.split("\\s+")[0].length() > 2 && haystack.contains(normalized.split("\\s+")[0]);
    }

    public record IncidentPattern(String service, String symptom, String risk, List<String> evidence) {}
    public record Recommendation(String action, String source, double confidence, String risk, String verification, String sourceRefs) {}
}
