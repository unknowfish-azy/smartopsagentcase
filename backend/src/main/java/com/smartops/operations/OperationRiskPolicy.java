package com.smartops.operations;

import java.util.Locale;
import java.util.regex.Pattern;

public class OperationRiskPolicy {
    public enum Risk { LOW, MEDIUM, HIGH, CRITICAL }

    private static final Pattern CRITICAL = Pattern.compile(
            "\\b(kubectl\\s+delete|drop\\s+(database|table|schema)|truncate\\b|rm\\s+-rf|docker\\s+system\\s+prune|shutdown|reboot)\\b",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern HIGH = Pattern.compile(
            "\\b(systemctl\\s+(stop|restart|disable)|docker\\s+(rm|stop|prune)|kubectl\\s+(delete|rollout\\s+restart)|chmod|chown|mv|rm)\\b",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern MEDIUM = Pattern.compile(
            "\\b(apt|yum|dnf|systemctl\\s+start|docker\\s+(start|restart)|kubectl\\s+apply|tee|sed\\s+-i)\\b",
            Pattern.CASE_INSENSITIVE);

    public Assessment assess(String command, boolean multiTarget, boolean productionTarget) {
        String normalized = command == null ? "" : command.trim().toLowerCase(Locale.ROOT);
        Risk risk = CRITICAL.matcher(normalized).find() ? Risk.CRITICAL
                : HIGH.matcher(normalized).find() ? Risk.HIGH
                : MEDIUM.matcher(normalized).find() ? Risk.MEDIUM
                : Risk.LOW;
        int approvals = risk == Risk.LOW ? 0 : (risk == Risk.CRITICAL ? 2 : 1);
        if (multiTarget && (productionTarget || risk == Risk.CRITICAL)) approvals = Math.max(approvals, 2);
        return new Assessment(risk, approvals);
    }

    public record Assessment(Risk risk, int requiredApprovals) {}
}
