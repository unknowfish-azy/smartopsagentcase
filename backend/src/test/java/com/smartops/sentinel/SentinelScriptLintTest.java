package com.smartops.sentinel;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 服务端脚本预检测试。
 *
 * <p>服务端才是把关人：前端预检只是即时反馈。因此这里的断言比前端更严格 ——
 * 命中高危规则的脚本必须连保存都不允许。</p>
 */
class SentinelScriptLintTest {

    @Test
    @DisplayName("声称要拦的高危写法必须真的被拦住，并说明命中哪一条")
    void blocksDangerousPatterns() {
        String[] blocked = {
                "rm -rf /",
                "sudo rm -rf /var/lib/mysql",
                "mkfs.ext4 /dev/sda1",
                "dd if=/dev/zero of=/dev/sda",
                "shutdown -h now",
                ":(){ :|:& };:",
                "iptables -F",
                "userdel ops",
                "DROP TABLE users;",
                "TRUNCATE TABLE orders;"
        };
        for (String body : blocked) {
            SentinelScriptLint.Verdict verdict = SentinelScriptLint.lint(body, "shell");
            assertEquals("blocked", verdict.status(), "must block: " + body);
            assertFalse(verdict.matches().isEmpty(), "must report which rule matched: " + body);
        }
    }

    @Test
    @DisplayName("只读类运维命令必须放行，不能把正常脚本也拦掉")
    void allowsReadOnlyOperations() {
        for (String body : new String[] { "df -h", "systemctl status nginx", "free -m", "cat /var/log/app.log | tail -n 50" }) {
            SentinelScriptLint.Verdict verdict = SentinelScriptLint.lint(body, "shell");
            assertEquals("ok", verdict.status(), "must allow: " + body);
            assertTrue(verdict.matches().isEmpty());
        }
    }

    @Test
    @DisplayName("空内容与不支持的语言按语法错误拒绝；语言缺省按 shell 处理")
    void rejectsEmptyAndUnsupported() {
        assertEquals("syntax_error", SentinelScriptLint.lint("", "shell").status());
        assertEquals("syntax_error", SentinelScriptLint.lint("   ", "shell").status());
        assertEquals("syntax_error", SentinelScriptLint.lint("echo hi", "ruby").status());
        // 与前端 localChallenge/编辑器默认值保持一致：不传语言视为 shell，而不是拒绝
        assertEquals("ok", SentinelScriptLint.lint("echo hi", null).status());
        assertEquals("ok", SentinelScriptLint.lint("echo hi", "SHELL").status());
    }

    @Test
    @DisplayName("括号不配对报语法错误；高危命中优先于语法提示")
    void syntaxHintAndDangerPrecedence() {
        assertEquals("syntax_error", SentinelScriptLint.lint("if [ -f /tmp/x ]; then echo $(date", "shell").status());
        // 高危命中更严重，不能被语法提示降级掩盖
        assertEquals("blocked", SentinelScriptLint.lint("rm -rf / (", "shell").status());
    }

    @Test
    @DisplayName("高危脚本需要管理员审批")
    void highRiskRequiresApproval() {
        assertTrue(SentinelScriptLint.requiresApproval("HIGH"));
        assertFalse(SentinelScriptLint.requiresApproval("MEDIUM"));
        assertFalse(SentinelScriptLint.requiresApproval("LOW"));
        assertFalse(SentinelScriptLint.requiresApproval(null));
    }

    @Test
    @DisplayName("自动发起处置绝不绕过审批闸门")
    void autoDispatchNeverBypassesApproval() {
        // 高危脚本：即使低危告警、开关打开、也已审批，也不能自动发起
        assertFalse(SentinelScriptLint.canAutoDispatch("P3", true, "HIGH", true));
        // 未审批脚本不能自动发起
        assertFalse(SentinelScriptLint.canAutoDispatch("P3", true, "LOW", false));
        // P0/P1 一律人工确认
        assertFalse(SentinelScriptLint.canAutoDispatch("P0", true, "LOW", true));
        assertFalse(SentinelScriptLint.canAutoDispatch("P1", true, "LOW", true));
        // 开关未打开不自动发起
        assertFalse(SentinelScriptLint.canAutoDispatch("P2", false, "LOW", true));
        // 只有低危级别 + 开关打开 + 低危脚本 + 已审批才允许（且仍走预览与审批）
        assertTrue(SentinelScriptLint.canAutoDispatch("P2", true, "LOW", true));
        assertTrue(SentinelScriptLint.canAutoDispatch("P3", true, "MEDIUM", true));
    }

    @Test
    @DisplayName("告警级别表把 P0/P1 标为必须人工确认")
    void severityTable() {
        var table = SentinelScriptLint.severityTable();
        assertEquals(Boolean.TRUE, table.get("P0"));
        assertEquals(Boolean.TRUE, table.get("P1"));
        assertEquals(Boolean.FALSE, table.get("P2"));
        assertEquals(Boolean.FALSE, table.get("P3"));
    }
}
