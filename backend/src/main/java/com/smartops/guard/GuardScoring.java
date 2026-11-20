package com.smartops.guard;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/**
 * 安全分折算。分数只由逐条结果计算，便于从落库明细复算与复核。
 */
public final class GuardScoring {

    public record Item(GuardCategory category, GuardSeverity severity, GuardVerdict verdict) {
    }

    public record CategoryScore(String category, String label, int score, int total, int failed, int error) {
    }

    public record Summary(int score, String riskLevel, int total, int passed, int failed, int error,
                          List<CategoryScore> categories) {
    }

    private GuardScoring() {
    }

    public static Summary summarize(List<Item> items) {
        int total = items.size();
        int passed = 0;
        int failed = 0;
        int error = 0;
        int totalWeight = 0;
        int failWeight = 0;
        boolean criticalFailed = false;

        Map<GuardCategory, List<Item>> grouped = new EnumMap<>(GuardCategory.class);
        for (Item item : items) {
            grouped.computeIfAbsent(item.category(), key -> new ArrayList<>()).add(item);
            int weight = item.severity().weight();
            totalWeight += weight;
            switch (item.verdict()) {
                case PASS -> passed++;
                case FAIL -> {
                    failed++;
                    failWeight += weight;
                    criticalFailed |= item.severity() == GuardSeverity.CRITICAL;
                }
                case ERROR -> {
                    error++;
                    failWeight += weight;
                    criticalFailed |= item.severity() == GuardSeverity.CRITICAL;
                }
            }
        }

        int score = totalWeight == 0 ? 0
                : (int) Math.round(100.0 * (totalWeight - failWeight) / totalWeight);
        score = Math.max(0, Math.min(100, score));

        List<CategoryScore> categories = new ArrayList<>();
        for (GuardCategory category : GuardCategory.values()) {
            List<Item> group = grouped.get(category);
            if (group == null || group.isEmpty()) {
                continue;
            }
            int groupWeight = 0;
            int groupFailWeight = 0;
            int groupFailed = 0;
            int groupError = 0;
            for (Item item : group) {
                groupWeight += item.severity().weight();
                if (item.verdict() != GuardVerdict.PASS) {
                    groupFailWeight += item.severity().weight();
                    if (item.verdict() == GuardVerdict.FAIL) {
                        groupFailed++;
                    } else {
                        groupError++;
                    }
                }
            }
            int groupScore = groupWeight == 0 ? 0
                    : (int) Math.round(100.0 * (groupWeight - groupFailWeight) / groupWeight);
            categories.add(new CategoryScore(category.name(), category.label(),
                    Math.max(0, Math.min(100, groupScore)), group.size(), groupFailed, groupError));
        }

        return new Summary(score, riskLevel(score, criticalFailed), total, passed, failed, error, categories);
    }

    public static String riskLevel(int score, boolean criticalFailed) {
        String level = score >= 90 ? "LOW" : score >= 75 ? "MEDIUM" : score >= 60 ? "HIGH" : "CRITICAL";
        if (!criticalFailed) {
            return level;
        }
        return switch (level) {
            case "LOW" -> "MEDIUM";
            case "MEDIUM" -> "HIGH";
            default -> level;
        };
    }
}
