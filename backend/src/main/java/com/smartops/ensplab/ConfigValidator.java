package com.smartops.ensplab;

import org.springframework.stereotype.Component;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * 基于教材命令规则库的 VRP 配置校验器。
 *
 * <p>规则来自 resources/ensp/kb/commands.json：每条规则给出正则 match、允许视图
 * contexts（空 = 任意视图）与 enter（进入目标视图 / parent / user / null）。
 * 校验时维护一个视图栈，逐行判定 OK / WRONG_CONTEXT / UNKNOWN / IGNORED，
 * 并可把整段输入与实验步骤的期望命令做集合比对，输出得分与缺失项。</p>
 *
 * <p>对 eNSP 教材答案里常见的缩写（sy / sa / dis / int / un / ter / mo / q）
 * 做一次性还原后再匹配；无法识别的命令只给提示，不误判为非法配置。</p>
 */
@Component
public class ConfigValidator {

    /** 常见 VRP 缩写还原，仅在第一轮规则未命中时使用。 */
    private static final Map<String, String> ALIASES = Map.ofEntries(
            Map.entry("sy", "system-view"),
            Map.entry("sa", "save"),
            Map.entry("dis", "display"),
            Map.entry("int", "interface"),
            Map.entry("un", "undo"),
            Map.entry("ter", "terminal"),
            Map.entry("mo", "monitor"),
            Map.entry("q", "quit"));

    private static final Set<String> OUTPUT_MARKERS = Set.of(
            "Info:", "Info(", "Error:", "Error(", "Warning:", "%",
            "The ", "Are you sure", "It will take", "Configuration file",
            "Note:", "Success", "Failed", "Login ", "Password:", "Username:",
            "Complete", "Enter ");

    private final EnspKnowledgeBase kb;
    private final List<CompiledRule> compiled = new ArrayList<>();

    public ConfigValidator(EnspKnowledgeBase kb) {
        this.kb = kb;
        for (EnspModels.Rule rule : kb.rules().rules()) {
            if (rule.match() == null || rule.match().isBlank()) {
                continue;
            }
            try {
                compiled.add(new CompiledRule(rule, Pattern.compile(rule.match(), Pattern.CASE_INSENSITIVE)));
            } catch (Exception ignored) {
                // 规则库中的坏正则跳过该条，不让整个知识库加载失败
            }
        }
    }

    /**
     * 逐行校验一段配置（可能带设备提示符与回显），返回最终视图与统计。
     */
    public ValidationReport validate(List<String> inputs, String startContext) {
        Deque<String> stack = new ArrayDeque<>();
        stack.push(normalizeContext(startContext));
        List<LineResult> lines = new ArrayList<>();
        int checked = 0;
        int ok = 0;

        for (int i = 0; i < inputs.size(); i++) {
            String raw = inputs.get(i) == null ? "" : inputs.get(i);
            LineResult result = evaluate(raw, stack.peek(), i + 1);
            lines.add(result);
            if ("OK".equals(result.status())) {
                checked++;
                ok++;
            } else if (!"IGNORED".equals(result.status())) {
                checked++;
            }
            applyEnter(result.enter(), stack);
        }

        int score = checked == 0 ? 100 : (int) Math.round(100.0 * ok / checked);
        return new ValidationReport(lines, checked, ok, List.of(), List.of(),
                List.of(), stack.peek(), score, score >= 80, List.of());
    }

    /**
     * 把整段输入与某个实验的期望命令比对，给出得分、缺失/多余命令与分步进度。
     */
    public ValidationReport validateExperiment(String experimentId, List<String> inputs) {
        EnspModels.Experiment experiment = kb.experiments().stream()
                .map(EnspKnowledgeBase.ExperimentHit::experiment)
                .filter(e -> e.id().equals(experimentId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("EXPERIMENT_NOT_FOUND: " + experimentId));

        ValidationReport base = validate(inputs, "user");
        Set<String> actual = new LinkedHashSet<>();
        for (LineResult line : base.lines()) {
            if ("OK".equals(line.status())) {
                actual.add(normalizeCommand(line.command()));
            }
        }

        Map<String, String> expectedByNormalized = new LinkedHashMap<>();
        List<StepProgress> steps = new ArrayList<>();
        for (EnspModels.Step step : experiment.steps()) {
            List<String> missingInStep = new ArrayList<>();
            for (String command : step.commands()) {
                String normalized = normalizeCommand(command);
                expectedByNormalized.putIfAbsent(normalized, command);
                if (!actual.contains(normalized)) {
                    missingInStep.add(command);
                }
            }
            steps.add(new StepProgress(step.seq(), step.title(), missingInStep.isEmpty(), missingInStep));
        }

        List<String> expectedDistinct = new ArrayList<>(expectedByNormalized.keySet());
        Set<String> expectedSet = new LinkedHashSet<>(expectedDistinct);
        long matched = expectedDistinct.stream().filter(actual::contains).count();
        List<String> missing = expectedDistinct.stream()
                .filter(c -> !actual.contains(c))
                .map(expectedByNormalized::get)
                .toList();
        List<String> extra = actual.stream().filter(c -> !expectedSet.contains(c)).toList();

        int total = expectedDistinct.size();
        int score = total == 0 ? 100 : (int) Math.round(100.0 * matched / total);

        List<String> suggestions = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (StepProgress step : steps) {
            if (step.done() || suggestions.size() >= 5) {
                continue;
            }
            experiment.steps().stream()
                    .filter(s -> s.seq() == step.seq())
                    .findFirst()
                    .map(EnspModels.Step::hint)
                    .filter(hint -> hint != null && !hint.isBlank())
                    .ifPresent(hint -> {
                        String text = "步骤 " + step.seq() + " 提示：" + hint;
                        if (seen.add(text)) {
                            suggestions.add(text);
                        }
                    });
        }
        long wrongContext = base.lines().stream().filter(l -> "WRONG_CONTEXT".equals(l.status())).count();
        if (wrongContext > 0) {
            suggestions.add("有 " + wrongContext + " 条命令在错误的视图下执行，请先 return 回到用户视图再进入正确视图。");
        }
        if (experiment.commonErrors() != null) {
            for (String error : experiment.commonErrors()) {
                if (suggestions.size() >= 8) {
                    break;
                }
                if (seen.add(error)) {
                    suggestions.add("常见错误：" + error);
                }
            }
        }

        return new ValidationReport(base.lines(), base.checked(), base.ok(), missing, extra,
                List.copyOf(suggestions), base.context(), score, missing.isEmpty(), steps);
    }

    /** 单行即时校验：前端边输边查时调用，调用方自行维护当前视图。 */
    public LineResult checkLine(String input, String context) {
        return evaluate(input, normalizeContext(context), 0);
    }

    private LineResult evaluate(String raw, String context, int lineNo) {
        String cleaned = stripPrompt(raw).trim();
        if (cleaned.isEmpty()) {
            return new LineResult(lineNo, raw, "IGNORED", "空行", null, context, "", null);
        }
        if (cleaned.startsWith("!") || cleaned.startsWith("#")) {
            return new LineResult(lineNo, raw, "IGNORED", "注释 / 分隔行", null, context, cleaned, null);
        }
        if (isOutputLine(cleaned)) {
            return new LineResult(lineNo, raw, "IGNORED", "设备回显 / 提示信息", null, context, cleaned, null);
        }

        MatchOutcome outcome = match(cleaned, context);
        if (outcome == null) {
            return new LineResult(lineNo, raw, "UNKNOWN",
                    "未识别的命令：" + cleaned + "（可尝试补全缩写或检查拼写）", null, context, cleaned, null);
        }
        if (!outcome.inContext()) {
            String expected = String.join("/", outcome.expectedContexts());
            return new LineResult(lineNo, raw, "WRONG_CONTEXT",
                    "命令「" + outcome.rule().cmd() + "」需要在 " + expected + " 视图下执行，当前是 " + context + " 视图",
                    outcome.rule().cmd(), context, outcome.effectiveCommand(), outcome.rule().enter());
        }
        return new LineResult(lineNo, raw, "OK", outcome.rule().desc(), outcome.rule().cmd(),
                applyEnter(outcome.rule().enter(), context), outcome.effectiveCommand(), outcome.rule().enter());
    }

    private MatchOutcome match(String command, String context) {
        MatchOutcome outcome = firstMatch(command, context);
        if (outcome != null) {
            return outcome;
        }
        String expanded = expandAliases(command);
        if (!expanded.equals(command)) {
            return firstMatch(expanded, context);
        }
        return null;
    }

    private MatchOutcome firstMatch(String command, String context) {
        List<EnspModels.Rule> hits = new ArrayList<>();
        for (CompiledRule rule : compiled) {
            if (rule.pattern().matcher(command).matches()) {
                hits.add(rule.rule());
            }
        }
        if (hits.isEmpty()) {
            return null;
        }
        Optional<EnspModels.Rule> scoped = hits.stream().filter(r -> inContext(r, context)).findFirst();
        if (scoped.isPresent()) {
            return new MatchOutcome(scoped.get(), true, List.of(), command);
        }
        Set<String> expected = new LinkedHashSet<>();
        for (EnspModels.Rule rule : hits) {
            if (rule.contexts() != null) {
                expected.addAll(rule.contexts());
            }
        }
        return new MatchOutcome(hits.get(0), false, List.copyOf(expected), command);
    }

    private static boolean inContext(EnspModels.Rule rule, String context) {
        return rule.contexts() == null || rule.contexts().isEmpty() || rule.contexts().contains(context);
    }

    private static String applyEnter(String enter, String currentContext) {
        return enter == null || enter.isBlank() || "null".equalsIgnoreCase(enter)
                ? currentContext
                : enter;
    }

    private void applyEnter(String enter, Deque<String> stack) {
        if (enter == null || enter.isBlank() || "null".equalsIgnoreCase(enter)) {
            return;
        }
        switch (enter) {
            case "parent" -> {
                if (stack.size() > 1) {
                    stack.pop();
                }
            }
            case "user" -> {
                stack.clear();
                stack.push("user");
            }
            default -> stack.push(enter);
        }
    }

    /** 去掉一行开头的 <Huawei> / [R1-GigabitEthernet0/0/0.101] 设备提示符。 */
    private static String stripPrompt(String line) {
        String value = line;
        while (true) {
            String trimmed = value.stripLeading();
            if (trimmed.length() > 1 && (trimmed.charAt(0) == '<' || trimmed.charAt(0) == '[')) {
                char closeChar = trimmed.charAt(0) == '<' ? '>' : ']';
                int close = trimmed.indexOf(closeChar);
                if (close > 0) {
                    value = trimmed.substring(close + 1);
                    continue;
                }
            }
            return value;
        }
    }

    private static boolean isOutputLine(String line) {
        if (line.startsWith("  ") || line.contains("........")) {
            return true;
        }
        for (String marker : OUTPUT_MARKERS) {
            if (line.startsWith(marker)) {
                return true;
            }
        }
        return false;
    }

    private static String normalizeContext(String context) {
        if (context == null || context.isBlank()) {
            return "user";
        }
        return context.trim().toLowerCase();
    }

    /** 归一化用于集合比对：压缩空白并小写，容忍大小写与多空格差异。 */
    public static String normalizeCommand(String command) {
        String cleaned = stripPrompt(command == null ? "" : command).trim();
        return cleaned.replaceAll("\\s+", " ").toLowerCase();
    }

    private static String expandAliases(String command) {
        String[] tokens = command.split("\\s+");
        StringBuilder sb = new StringBuilder();
        for (String token : tokens) {
            String lower = token.toLowerCase();
            sb.append(ALIASES.getOrDefault(lower, token)).append(' ');
        }
        return sb.toString().trim();
    }

    private record CompiledRule(EnspModels.Rule rule, Pattern pattern) {
    }

    private record MatchOutcome(EnspModels.Rule rule, boolean inContext,
                                List<String> expectedContexts, String effectiveCommand) {
    }

    public record LineResult(int line, String input, String status, String message, String matched,
                             String contextAfter, String command, String enter) {
    }

    public record StepProgress(int seq, String title, boolean done, List<String> missing) {
    }

    public record ValidationReport(List<LineResult> lines, int checked, int ok,
                                   List<String> missing, List<String> extra,
                                   List<String> suggestions, String context, int score,
                                   boolean pass, List<StepProgress> steps) {
    }
}
