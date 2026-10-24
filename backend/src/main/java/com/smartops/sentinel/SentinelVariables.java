package com.smartops.sentinel;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 平台变量替换。
 *
 * <p>把脚本里的 {@code ${主机IP}}、{@code ${告警指标}}、{@code ${告警值}} 等占位符
 * 替换成运行时上下文。与前端 {@code applyVariables} 同一条语义，但**服务端是权威**：
 * 前端替换只用于预览展示，真正送进执行链的是这里的结果。</p>
 *
 * <p><b>为什么不做 shell 展开</b>：这些变量来自告警与资产信息，直接拼进 shell 会被
 * 命令替换利用（例如告警值里带 {@code $(...)}）。因此这里做的是"按已知变量名精确替换"，
 * 并且对替换结果做**危险字符检测**——宁可拒绝，也不把外部文本当代码执行。</p>
 */
public final class SentinelVariables {

    private SentinelVariables() {}

    /** 支持的变量名（不含 ${} 包裹）。未知变量保持原样，不静默清空。 */
    public static final List<String> SUPPORTED = List.of(
            "主机IP", "主机名", "告警指标", "告警值", "阈值", "告警级别", "告警标题", "脚本名", "执行人", "时间");

    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{([^{}]+)}");

    /** 替换后会破坏命令语义的字符：换行、反引号、命令替换、重定向、管道。 */
    private static final Pattern UNSAFE = Pattern.compile("[\\r\\n`]|\\$\\(|\\|\\s*sh\\b|[;&]\\s*(rm|shutdown|reboot)\\b");

    /** 替换结果。{@code unresolved} 列出未识别的变量，供界面提示。 */
    public record Result(String body, List<String> unresolved, List<String> replaced) {}

    /** 只替换，不校验（用于界面预览）。 */
    public static Result apply(String body, Map<String, String> variables) {
        if (body == null) return new Result("", List.of(), List.of());
        Map<String, String> safe = variables == null ? Map.of() : variables;
        List<String> unresolved = new ArrayList<>();
        List<String> replaced = new ArrayList<>();
        Matcher matcher = PLACEHOLDER.matcher(body);
        StringBuilder output = new StringBuilder();
        while (matcher.find()) {
            String name = matcher.group(1).trim();
            String value = safe.get(name);
            if (value == null) {
                unresolved.add(name);
                matcher.appendReplacement(output, Matcher.quoteReplacement(matcher.group()));
            } else {
                replaced.add(name);
                matcher.appendReplacement(output, Matcher.quoteReplacement(value));
            }
        }
        matcher.appendTail(output);
        return new Result(output.toString(), List.copyOf(unresolved), List.copyOf(replaced));
    }

    /**
     * 替换并校验：替换进来的外部文本若含有命令控制字符，直接拒绝。
     *
     * @throws IllegalArgumentException 变量值不安全时抛出，调用方应转成 400
     */
    public static Result applyChecked(String body, Map<String, String> variables) {
        Result result = apply(body, variables);
        for (String name : result.replaced()) {
            String value = variables.get(name);
            if (value == null) continue;
            if (UNSAFE.matcher(value).find()) {
                throw new IllegalArgumentException("变量「" + name + "」的值含有命令控制字符，已拒绝：" + preview(value));
            }
        }
        return result;
    }

    /** 必填变量是否都提供了。 */
    public static List<String> missing(Set<String> required, Map<String, String> variables) {
        if (required == null || required.isEmpty()) return List.of();
        Map<String, String> safe = variables == null ? Map.of() : variables;
        return required.stream().filter(name -> !safe.containsKey(name)).sorted().toList();
    }

    /**
     * 校验定时表达式（5 段：分 时 日 月 周）。
     *
     * <p>只做形状校验，不宣称完整 cron 语义；真正的调度由调度器解释。</p>
     */
    public static boolean validCron(String expression) {
        if (expression == null) return false;
        String[] parts = expression.trim().split("\\s+");
        if (parts.length != 5) return false;
        for (String part : parts) {
            if (!part.matches("[0-9*/,\\-]+")) return false;
        }
        return true;
    }

    private static String preview(String value) {
        return value.length() <= 40 ? value : value.substring(0, 40);
    }
}
