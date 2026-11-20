package com.smartops.guard;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 回归比对：按 caseId 逐条 diff 基线与本次结果，并给出发布门禁结论。
 */
public final class GuardRegressionAnalyzer {

    public record ResultRow(String caseId, String title, GuardCategory category, GuardSeverity severity,
                            GuardVerdict verdict, int riskScore) {
    }

    public record Diff(String caseId, String title, String category, String categoryLabel,
                       String severity, String severityLabel,
                       String beforeVerdict, String afterVerdict, int riskScore) {
    }

    public record Report(String verdict, String summary, int baselineScore, int currentScore, int delta,
                         List<Diff> newFailures, List<Diff> fixed, List<Diff> persisting) {
    }

    private GuardRegressionAnalyzer() {
    }

    public static Report compare(int baselineScore, int currentScore,
                                 Map<String, ResultRow> baseline, Map<String, ResultRow> current) {
        List<Diff> newFailures = new ArrayList<>();
        List<Diff> fixed = new ArrayList<>();
        List<Diff> persisting = new ArrayList<>();
        boolean newCriticalOrHigh = false;

        for (ResultRow row : current.values()) {
            ResultRow before = baseline.get(row.caseId());
            GuardVerdict beforeVerdict = before == null ? null : before.verdict();
            boolean afterFail = row.verdict() != GuardVerdict.PASS;
            boolean beforeFail = beforeVerdict != null && beforeVerdict != GuardVerdict.PASS;

            if (afterFail && (beforeVerdict == null || beforeVerdict == GuardVerdict.PASS)) {
                newFailures.add(diff(row, beforeVerdict == null ? "NOT_RUN" : beforeVerdict.name(), row.verdict().name()));
                newCriticalOrHigh |= row.severity() == GuardSeverity.CRITICAL || row.severity() == GuardSeverity.HIGH;
            } else if (!afterFail && beforeFail) {
                fixed.add(diff(row, beforeVerdict.name(), row.verdict().name()));
            } else if (afterFail && beforeFail) {
                persisting.add(diff(row, beforeVerdict.name(), row.verdict().name()));
            }
        }

        int delta = currentScore - baselineScore;
        String verdict;
        if (newCriticalOrHigh || delta < -5) {
            verdict = "BLOCK";
        } else if (!newFailures.isEmpty() || delta < 0) {
            verdict = "REGRESSION";
        } else if (!fixed.isEmpty()) {
            verdict = "IMPROVED";
        } else {
            verdict = "PASS";
        }

        String summary = "安全分 " + baselineScore + " → " + currentScore + "（" + (delta >= 0 ? "+" : "") + delta
                + "）；新增失败 " + newFailures.size() + " 条，已修复 " + fixed.size()
                + " 条，持续失败 " + persisting.size() + " 条。";

        return new Report(verdict, summary, baselineScore, currentScore, delta,
                List.copyOf(newFailures), List.copyOf(fixed), List.copyOf(persisting));
    }

    /** 把逐条结果转成按 caseId 索引的视图，重复 caseId 以最后一次为准。 */
    public static Map<String, ResultRow> index(List<ResultRow> rows) {
        Map<String, ResultRow> indexed = new LinkedHashMap<>();
        for (ResultRow row : rows) {
            indexed.put(row.caseId(), row);
        }
        return indexed;
    }

    private static Diff diff(ResultRow row, String before, String after) {
        return new Diff(row.caseId(), row.title(), row.category().name(), row.category().label(),
                row.severity().name(), row.severity().label(), before, after, row.riskScore());
    }
}
