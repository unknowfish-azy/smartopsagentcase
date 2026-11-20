package com.smartops.guard;

/**
 * 一条安全的测评用例。用例只描述「问什么」与「期望什么」，判定规则集中在
 * {@link GuardDetector}，保证同一用例在任何目标上口径一致。
 */
public record GuardCase(
        String id,
        GuardCategory category,
        GuardSeverity severity,
        String title,
        String systemPrompt,
        String prompt,
        GuardDetector.Kind detector,
        String expected
) {
}
