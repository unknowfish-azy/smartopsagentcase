package com.smartops.service;

import com.smartops.security.SessionUser;
import com.smartops.security.SecurityAuditService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 处置动作风险评估服务（P0-3）。
 *
 * <p>设计原则：
 * <ul>
 *   <li>确定性硬规则 + 可解释评分，不训练神经网络，不输出伪精确概率；</li>
 *   <li>BLOCK 级拦截不可被 Kimi 或任何下游调用方覆盖；</li>
 *   <li>所有评估结果落审计日志，支持事后追溯；</li>
 *   <li>输入为「当前故障状态 + 拟执行动作」，输出为风险等级 + 命中规则 + 处置建议。</li>
 * </ul>
 *
 * <p>风险等级：LOW（自动放行）、MEDIUM（需审批）、HIGH（需高级审批）、BLOCK（硬拦截）。
 */
@Service
public class RiskAssessmentService {

    private final JdbcTemplate jdbc;
    private final SecurityAuditService audit;

    @Autowired
    public RiskAssessmentService(JdbcTemplate jdbc, SecurityAuditService audit) {
        this.jdbc = jdbc;
        this.audit = audit;
    }

    /** 测试用无审计构造。 */
    RiskAssessmentService(JdbcTemplate jdbc) {
        this(jdbc, null);
    }

    // ── 硬规则：命中即 BLOCK，不可绕过 ──

    private static final List<BlockRule> BLOCK_RULES = List.of(
            new BlockRule("RM_RF_ROOT", "递归删除根目录或系统目录",
                    Pattern.compile("rm\\s+(-[a-zA-Z]*[rf][a-zA-Z]*\\s+)*\\s*/(\\s|$|\\*)")),
            new BlockRule("DD_DISK", "dd 直接写磁盘设备",
                    Pattern.compile("dd\\s+.*of=/dev/[sh]d[a-z]")),
            new BlockRule("MKFS", "格式化文件系统",
                    Pattern.compile("mkfs[.\\s]")),
            new BlockRule("DROP_DATABASE", "DROP DATABASE/TABLE 无 WHERE 保护",
                    Pattern.compile("(?i)DROP\\s+(DATABASE|TABLE)\\s+(?!IF\\s)")),
            new BlockRule("FORK_BOMB", "fork 炸弹",
                    Pattern.compile(":\\(\\)\\s*\\{\\s*:\\|:")),
            new BlockRule("SHUTDOWN_PROD", "生产环境关机/重启",
                    Pattern.compile("(?i)(shutdown|reboot|halt|poweroff)\\s")),
            new BlockRule("IPTABLES_FLUSH", "清空防火墙规则",
                    Pattern.compile("iptables\\s+(-F|--flush)")),
            new BlockRule("KILL_ALL", "kill 所有进程",
                    Pattern.compile("kill\\s+(-9\\s+)?-1\\b"))
    );

    // ── 评分规则：累加分数，映射到风险等级 ──

    private static final List<ScoreRule> SCORE_RULES = List.of(
            new ScoreRule("PROD_ENV", "目标环境为生产", 30,
                    Pattern.compile("(?i)prod|production")),
            new ScoreRule("RM_RF", "递归强制删除", 40,
                    Pattern.compile("rm\\s+-[a-zA-Z]*[rf]")),
            new ScoreRule("SYSTEMCTL_STOP", "停止系统服务", 25,
                    Pattern.compile("systemctl\\s+(stop|disable|mask)")),
            new ScoreRule("KILL_SIGNAL", "发送 kill 信号", 20,
                    Pattern.compile("kill\\s+-[0-9]")),
            new ScoreRule("CHMOD_777", "开放全权限", 30,
                    Pattern.compile("chmod\\s+(-R\\s+)?777")),
            new ScoreRule("CURL_PIPE_SH", "远程脚本管道执行", 45,
                    Pattern.compile("(curl|wget)\\s+.*\\|\\s*(ba)?sh")),
            new ScoreRule("WRITE_CONFIG", "写入系统配置文件", 20,
                    Pattern.compile(">\\s*/(etc|sys|proc)/")),
            new ScoreRule("DOCKER_RM", "删除容器", 25,
                    Pattern.compile("docker\\s+rm\\s")),
            new ScoreRule("KUBECTL_DELETE", "删除 K8s 资源", 30,
                    Pattern.compile("kubectl\\s+delete\\s")),
            new ScoreRule("GIT_FORCE", "Git 强制推送", 35,
                    Pattern.compile("git\\s+push\\s+.*--force")),
            new ScoreRule("SQL_WRITE", "SQL 写操作", 15,
                    Pattern.compile("(?i)(INSERT|UPDATE|DELETE|ALTER|TRUNCATE)\\s")),
            new ScoreRule("NETWORK_EXPOSE", "暴露网络端口", 20,
                    Pattern.compile("(?i)(0\\.0\\.0\\.0|--publish|\\s-p\\s+\\d+)"))
    );

    /**
     * 评估处置动作风险。
     *
     * @param userId    操作用户
     * @param command   拟执行命令
     * @param toolId    工具标识
     * @param context   上下文信息（环境、服务名等）
     * @return 风险评估结果
     */
    public RiskResult assess(Long userId, String command, String toolId, Map<String, String> context) {
        if (command == null || command.isBlank()) {
            return new RiskResult("LOW", 0, List.of(), "空命令，无风险", true);
        }

        // 1. 硬规则检查 — 命中即 BLOCK
        for (BlockRule rule : BLOCK_RULES) {
            if (rule.pattern.matcher(command).find()) {
                RiskResult result = new RiskResult("BLOCK", 100, List.of(rule.id),
                        "命中硬规则: " + rule.description, false);
                recordAssessment(userId, command, toolId, result);
                return result;
            }
        }

        // 2. 评分规则 — 累加分数
        int totalScore = 0;
        List<String> hitRules = new java.util.ArrayList<>();
        StringBuilder reasons = new StringBuilder();

        for (ScoreRule rule : SCORE_RULES) {
            if (rule.pattern.matcher(command).find()) {
                totalScore += rule.score;
                hitRules.add(rule.id);
                if (reasons.length() > 0) reasons.append("; ");
                reasons.append(rule.description).append("(+").append(rule.score).append(")");
            }
        }

        // 上下文加分
        if (context != null) {
            String env = context.getOrDefault("environment", "");
            if ("prod".equalsIgnoreCase(env) || "production".equalsIgnoreCase(env)) {
                totalScore += 20;
                hitRules.add("CTX_PROD");
                if (reasons.length() > 0) reasons.append("; ");
                reasons.append("生产环境(+20)");
            }
        }

        // 3. 映射等级
        String level;
        boolean allowed;
        if (totalScore >= 60) {
            level = "HIGH";
            allowed = false;
        } else if (totalScore >= 30) {
            level = "MEDIUM";
            allowed = true; // 需审批但允许
        } else {
            level = "LOW";
            allowed = true;
        }

        RiskResult result = new RiskResult(level, totalScore, hitRules,
                reasons.length() > 0 ? reasons.toString() : "未命中风险规则", allowed);
        recordAssessment(userId, command, toolId, result);
        return result;
    }

    /**
     * 快速检查：命令是否被硬规则拦截。
     * 用于 Agent 输出最终处置方案前的预检。
     */
    public boolean isBlocked(String command) {
        if (command == null || command.isBlank()) return false;
        return BLOCK_RULES.stream().anyMatch(rule -> rule.pattern.matcher(command).find());
    }

    private void recordAssessment(Long userId, String command, String toolId, RiskResult result) {
        try {
            jdbc.update(
                    "INSERT INTO risk_assessment_log(user_id,tool_id,command_text,risk_level,risk_score,hit_rules,allowed,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    userId, toolId,
                    command.length() > 2000 ? command.substring(0, 2000) : command,
                    result.level, result.score,
                    String.join(",", result.hitRules),
                    result.allowed, Timestamp.from(Instant.now()));
        } catch (Exception ignored) {
            // 审计日志写入失败不阻塞主流程，但 BLOCK 结果仍然生效
        }
        if (audit != null && ("BLOCK".equals(result.level) || "HIGH".equals(result.level))) {
            try {
                audit.record(userId == null ? null : new SessionUser(userId, null, null),
                        "RISK_ASSESSMENT_" + result.level, toolId,
                        result.allowed ? "ALLOWED" : "DENIED",
                        "score=" + result.score + "; rules=" + String.join(",", result.hitRules));
            } catch (Exception ignored) { }
        }
    }

    // ── 内部记录类型 ──

    private record BlockRule(String id, String description, Pattern pattern) {}
    private record ScoreRule(String id, String description, int score, Pattern pattern) {}

    /** 风险评估结果。 */
    public record RiskResult(String level, int score, List<String> hitRules, String reason, boolean allowed) {
        public boolean isBlocked() { return "BLOCK".equals(level); }
        public boolean requiresApproval() { return "MEDIUM".equals(level) || "HIGH".equals(level); }
    }
}
