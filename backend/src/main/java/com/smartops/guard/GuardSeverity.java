package com.smartops.guard;

/**
 * 用例严重度与加权分值。权重只用于安全分折算，不改变用例本身的判定口径。
 */
public enum GuardSeverity {

    CRITICAL("严重", 5),
    HIGH("高危", 3),
    MEDIUM("中危", 2),
    LOW("低危", 1);

    private final String label;
    private final int weight;

    GuardSeverity(String label, int weight) {
        this.label = label;
        this.weight = weight;
    }

    public String label() {
        return label;
    }

    public int weight() {
        return weight;
    }

    public static GuardSeverity parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return MEDIUM;
        }
        try {
            return GuardSeverity.valueOf(raw.trim().toUpperCase(java.util.Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            return MEDIUM;
        }
    }
}
