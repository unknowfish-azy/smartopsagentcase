package com.smartops.sentinel;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 脚本高危预检（服务端版本）。
 *
 * <p>与前端 {@code lintScript} 同一批规则，但**服务端才是把关人**：前端预检只是即时反馈，
 * 真正拒绝保存与执行的判定在这里。</p>
 *
 * <p>必须说清的边界：这是**防御性预检，不是沙箱**。它拦住明显的误操作与最危险的写法；
 * 真正的执行边界仍在既有链路上 —— 固定命令、参数校验、最小权限、超时、预览与人工审批。</p>
 */
public final class SentinelScriptLint {

    private SentinelScriptLint() {}

    public record Match(String label, String sample) {}

    public record Verdict(String status, List<Match> matches, String detail) {
        public boolean blocked() { return "blocked".equals(status); }
        public boolean ok() { return "ok".equals(status); }
    }

    private record Danger(String label, Pattern pattern) {}

    private static final List<Danger> DANGEROUS = List.of(
            new Danger("递归删除文件（rm -rf）", Pattern.compile("\\brm\\s+(-[a-zA-Z]*\\s+)*-[a-zA-Z]*[rf]", Pattern.CASE_INSENSITIVE)),
            new Danger("删除根目录内容", Pattern.compile("\\brm\\s+-[a-zA-Z]*f\\s+/(?!\\w)", Pattern.CASE_INSENSITIVE)),
            new Danger("格式化文件系统（mkfs）", Pattern.compile("\\bmkfs(\\.\\w+)?\\b", Pattern.CASE_INSENSITIVE)),
            new Danger("向块设备裸写（dd of=/dev/…）", Pattern.compile("\\bdd\\b[^\\n]*\\bof=/dev/", Pattern.CASE_INSENSITIVE)),
            new Danger("重定向覆盖磁盘设备", Pattern.compile(">\\s*/dev/[sh]d[a-z]", Pattern.CASE_INSENSITIVE)),
            new Danger("关机或重启主机", Pattern.compile("\\b(shutdown|reboot|halt|poweroff)\\b", Pattern.CASE_INSENSITIVE)),
            new Danger("Fork 炸弹", Pattern.compile(":\\(\\)\\s*\\{\\s*:\\|:&\\s*\\}\\s*;\\s*:")),
            new Danger("把根目录权限设为 777", Pattern.compile("\\bchmod\\s+(-[a-zA-Z]*\\s+)*777\\s+/", Pattern.CASE_INSENSITIVE)),
            new Danger("清空防火墙规则", Pattern.compile("\\b(iptables|nft)\\b[^\\n]*\\s-F\\b", Pattern.CASE_INSENSITIVE)),
            new Danger("删除用户或用户组", Pattern.compile("\\b(userdel|groupdel)\\b", Pattern.CASE_INSENSITIVE)),
            new Danger("删除数据库对象", Pattern.compile("\\bDROP\\s+(TABLE|DATABASE)\\b", Pattern.CASE_INSENSITIVE)),
            new Danger("清空数据表", Pattern.compile("\\bTRUNCATE\\s+TABLE\\b", Pattern.CASE_INSENSITIVE))
    );

    private static final List<String> LANGUAGES = List.of("shell", "python", "bat", "powershell");

    public static Verdict lint(String body, String language) {
        String normalized = language == null ? "shell" : language.toLowerCase(Locale.ROOT);
        if (!LANGUAGES.contains(normalized)) {
            return new Verdict("syntax_error", List.of(), "不支持的语言：" + language);
        }
        if (body == null || body.isBlank()) {
            return new Verdict("syntax_error", List.of(), "脚本内容为空");
        }
        List<Match> matches = new java.util.ArrayList<>();
        for (Danger danger : DANGEROUS) {
            var found = danger.pattern().matcher(body);
            if (found.find()) {
                String sample = found.group().trim();
                matches.add(new Match(danger.label(), sample.length() > 80 ? sample.substring(0, 80) : sample));
            }
        }
        if (!matches.isEmpty()) {
            return new Verdict("blocked", List.copyOf(matches), "命中 " + matches.size() + " 条高危规则，已拒绝保存或执行");
        }
        // 括号明显不配对只作为提示，不冒充真正的语法分析器。
        if (count(body, '(') != count(body, ')')) {
            return new Verdict("syntax_error", List.of(), "括号不配对，疑似语法错误（仅粗检）");
        }
        return new Verdict("ok", List.of(), "未命中高危规则；执行仍受参数校验、最小权限与超时约束");
    }

    private static int count(String text, char target) {
        int total = 0;
        for (int index = 0; index < text.length(); index++) if (text.charAt(index) == target) total++;
        return total;
    }

    /** 按风险级别判断是否需要管理员审批后才能用于告警联动。 */
    public static boolean requiresApproval(String riskLevel) {
        return "HIGH".equalsIgnoreCase(riskLevel == null ? "" : riskLevel);
    }

    /**
     * 是否允许"由策略自动发起处置"。
     *
     * <p>即使返回 true，也只是**免去人工点击发起**：脚本仍要经过既有
     * MultiExec 预览 + 审批 + 二次确认。这里不产生任何直接执行的通路。</p>
     */
    public static boolean canAutoDispatch(String severity, boolean autoDispatch, String scriptRisk, boolean scriptApproved) {
        if ("P0".equals(severity) || "P1".equals(severity)) return false;
        if (!autoDispatch) return false;
        if ("HIGH".equalsIgnoreCase(scriptRisk == null ? "" : scriptRisk)) return false;
        return scriptApproved;
    }

    /** 告警级别的默认处置门槛，供界面与告警规则共用。 */
    public static Map<String, Boolean> severityTable() {
        Map<String, Boolean> table = new LinkedHashMap<>();
        table.put("P0", true);
        table.put("P1", true);
        table.put("P2", false);
        table.put("P3", false);
        return table;
    }
}
