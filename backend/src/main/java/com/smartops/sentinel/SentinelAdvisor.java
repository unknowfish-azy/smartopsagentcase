package com.smartops.sentinel;

import com.smartops.service.IncidentRecommendationService;
import com.smartops.service.OperatorMemoryService;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * 告警研判（AI 辅助）。
 *
 * <p><b>定位必须说清</b>：这里输出的是**建议**，不是结论。界面与数据都把 `ai_summary`
 * 当建议展示，并附带证据来源；它不会、也不能自动执行任何操作 ——
 * 真正的执行仍要经既有「预览 → 审批 → 执行 → 验证 → 审计」链路。</p>
 *
 * <p>实现上没有另造一套"AI 推理"：复用既有的
 * {@link IncidentRecommendationService} 与运维记忆 {@link OperatorMemoryService}，
 * 把告警的指标、观测值、阈值翻译成它们认识的 {@code IncidentPattern}。
 * 这样"既往经验"与"告警研判"用的是同一份记忆，不会出现两套互相矛盾的建议。</p>
 */
@Service
public class SentinelAdvisor {

    private final IncidentRecommendationService incidentRecommendations;
    private final OperatorMemoryService memories;

    public SentinelAdvisor(IncidentRecommendationService incidentRecommendations, OperatorMemoryService memories) {
        this.incidentRecommendations = incidentRecommendations;
        this.memories = memories;
    }

    /** 一条候选处置脚本及其匹配理由（理由必须可解释，不能只给一个分数）。 */
    public record ScriptCandidate(long scriptId, String name, String riskLevel, String reason) {}

    /** 研判结果：结论 + 证据 + 推荐脚本 + 是否建议人工优先介入。 */
    public record Advice(long alertId, String severity, String summary, List<String> evidence,
                         List<ScriptCandidate> scripts, List<IncidentRecommendationService.Recommendation> memoryMatches,
                         boolean humanFirst, String disclaimer) {}

    /**
     * 对一条告警做研判。
     *
     * @param alert    告警（标题、指标、观测值、阈值、详情）
     * @param scripts  该用户可用的脚本（用于推荐，不代表已授权执行）
     * @param userId   记忆的归属用户
     */
    public Advice analyze(AlertFacts alert, List<ScriptFact> scripts, long userId) {
        List<String> evidence = new ArrayList<>();
        evidence.add("指标 " + safe(alert.metric()) + " = " + safe(alert.observedValue()));
        evidence.add("阈值 " + safe(alert.thresholdValue()));
        if (alert.detail() != null && !alert.detail().isBlank()) evidence.add("采样上下文：" + truncate(alert.detail(), 200));

        var pattern = new IncidentRecommendationService.IncidentPattern(
                safe(alert.metric()), safe(alert.title()), safe(alert.severity()), List.copyOf(evidence));
        var memoryMatches = incidentRecommendations.recommend(pattern, memories.list(userId));

        String haystack = (safe(alert.title()) + " " + safe(alert.metric()) + " " + safe(alert.observedValue()))
                .toLowerCase(Locale.ROOT);
        List<ScriptCandidate> candidates = new ArrayList<>();
        for (ScriptFact script : scripts) {
            String reason = matchReason(haystack, script);
            if (reason != null) {
                candidates.add(new ScriptCandidate(script.id(), script.name(), script.riskLevel(), reason));
            }
        }
        // 高风险脚本排在后面：推荐列表的顺序本身就在表达"先试低危的"。
        candidates.sort((left, right) -> Integer.compare(riskWeight(left.riskLevel()), riskWeight(right.riskLevel())));

        boolean humanFirst = "P0".equals(alert.severity()) || "P1".equals(alert.severity())
                || candidates.stream().anyMatch(candidate -> "HIGH".equalsIgnoreCase(candidate.riskLevel()));
        String summary = buildSummary(alert, candidates, memoryMatches, humanFirst);
        return new Advice(alert.id(), alert.severity(), summary, List.copyOf(evidence), List.copyOf(candidates),
                memoryMatches, humanFirst, disclaimer());
    }

    private static int riskWeight(String risk) {
        return switch (risk == null ? "" : risk.toUpperCase(Locale.ROOT)) {
            case "LOW" -> 0;
            case "MEDIUM" -> 1;
            default -> 2;
        };
    }

    /** 脚本匹配理由：名称/标签命中告警文本才算候选，并说明命中了哪个词。 */
    private static String matchReason(String haystack, ScriptFact script) {
        for (String token : tokens(script.name())) {
            if (token.length() >= 3 && haystack.contains(token)) return "脚本名称包含「" + token + "」";
        }
        for (String token : tokens(script.tags())) {
            if (token.length() >= 3 && haystack.contains(token)) return "脚本标签包含「" + token + "」";
        }
        return null;
    }

    private static List<String> tokens(String value) {
        if (value == null || value.isBlank()) return List.of();
        List<String> tokens = new ArrayList<>();
        for (String part : value.toLowerCase(Locale.ROOT).split("[^a-z0-9\\u4e00-\\u9fa5]+")) {
            if (!part.isBlank()) tokens.add(part);
        }
        return tokens;
    }

    private static String buildSummary(AlertFacts alert, List<ScriptCandidate> candidates,
                                       List<IncidentRecommendationService.Recommendation> memoryMatches, boolean humanFirst) {
        StringBuilder text = new StringBuilder();
        text.append("告警「").append(safe(alert.title())).append("」为 ").append(safe(alert.severity())).append(" 级，")
                .append("指标 ").append(safe(alert.metric())).append(" 当前 ").append(safe(alert.observedValue()))
                .append("，超过阈值 ").append(safe(alert.thresholdValue())).append("。");
        if (!memoryMatches.isEmpty()) {
            text.append("既往运维记忆中有 ").append(memoryMatches.size()).append(" 条相似处置经验，")
                    .append("其中置信度最高的建议是「").append(memoryMatches.get(0).action()).append("」（来源：")
                    .append(memoryMatches.get(0).source()).append("）。");
        } else {
            text.append("既往记忆中没有可直接复用的相似处置，本次需要人工判断。");
        }
        if (candidates.isEmpty()) {
            text.append("没有匹配到可推荐的处置脚本，请人工选择或先沉淀脚本。");
        } else {
            ScriptCandidate top = candidates.get(0);
            text.append("推荐脚本「").append(top.name()).append("」（").append(top.riskLevel()).append(" 风险，")
                    .append(top.reason()).append("）。");
            if (candidates.size() > 1) text.append("另有 ").append(candidates.size() - 1).append(" 个备选。");
        }
        text.append(humanFirst
                ? "该告警或候选脚本风险较高，建议人工确认后再发起处置。"
                : "可由人工发起处置；脚本仍需预览与审批后才能执行。");
        return text.toString();
    }

    static String disclaimer() {
        return "以上为 AI 辅助研判建议，不是既定结论；处置必须经人工确认与既有审批链执行。";
    }

    private static String safe(String value) { return value == null || value.isBlank() ? "—" : value; }

    static String truncate(String value, int max) {
        return value == null || value.length() <= max ? value : value.substring(0, max);
    }

    /** 告警事实（与持久化解耦，便于单元测试）。 */
    public record AlertFacts(long id, String severity, String title, String metric, String observedValue,
                             String thresholdValue, String detail) {}

    /** 脚本事实：只取推荐需要的字段。 */
    public record ScriptFact(long id, String name, String tags, String riskLevel) {}
}
