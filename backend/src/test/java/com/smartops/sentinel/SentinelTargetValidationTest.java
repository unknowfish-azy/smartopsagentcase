package com.smartops.sentinel;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 哨兵采集目标的白名单与注入防护测试。
 *
 * <p>这是本模块最重要的安全边界：**哨兵不接受任意 shell 命令**。
 * 采集命令由服务端按白名单指标名固定拼装；业务指标先经严格模式校验再拼接。</p>
 */
class SentinelTargetValidationTest {

    @Test
    @DisplayName("系统指标只接受白名单名字")
    void systemMetricsAreWhitelisted() {
        for (String metric : new String[] { "cpu", "memory", "disk", "disk_io", "network", "tcp" }) {
            assertEquals(metric, SentinelService.validateTarget("system", metric));
        }
        // 其它任何写法都拒绝
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("system", "load"));
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("system", "cpu; rm -rf /"));
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("system", "$(whoami)"));
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("system", ""));
    }

    @Test
    @DisplayName("业务指标：端口 / 进程 / URL 各用严格模式校验")
    void businessMetricsAreStrictlyValidated() {
        assertEquals("port:22", SentinelService.validateTarget("business", "port:22"));
        assertEquals("port:65535", SentinelService.validateTarget("business", "port:65535"));
        assertEquals("process:nginx", SentinelService.validateTarget("business", "process:nginx"));
        assertEquals("process:my-app_1", SentinelService.validateTarget("business", "process:my-app_1"));
        assertTrue(SentinelService.validateTarget("business", "http:https://ops.example.test/health").startsWith("http:"));

        // 端口越界或非数字
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("business", "port:70000"));
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("business", "port:22; rm -rf /"));
        // 进程名注入
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("business", "process:nginx; whoami"));
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("business", "process:$(id)"));
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("business", "process:../../etc/passwd"));
        // URL 必须是 http/https
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("business", "http:file:///etc/passwd"));
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("business", "PING:example.test"));
    }

    @Test
    @DisplayName("日志哨兵：路径受限，关键字必填")
    void logTargetAndKeyword() {
        assertEquals("/var/log/app.log", SentinelService.validateTarget("log", "/var/log/app.log"));
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("log", "/var/log/app.log; rm -rf /"));
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("log", "/var/log/$(id).log"));
    }

    @Test
    @DisplayName("采集命令不含未校验输入：系统指标走固定命令")
    void systemCommandIsFixed() {
        String command = SentinelService.collectionCommand("system", "cpu", null);
        assertEquals(SentinelService.SYSTEM_METRIC_COMMAND, command);
        // 固定命令里不应出现任何用户可控拼接
        assertFalse(command.contains("whoami"));
    }

    @Test
    @DisplayName("关键字与路径都经过单引号转义后拼接")
    void shellQuoteEscapesSingleQuotes() {
        assertEquals("'plain'", SentinelService.shellQuote("plain"));
        assertEquals("'it'\\''s'", SentinelService.shellQuote("it's"));
        // 通过转义后，即使关键字里带引号也无法闭合外围单引号
        String command = SentinelService.collectionCommand("log", "/var/log/app.log", "it's");
        assertTrue(command.contains("'it'\\''s'"));
        assertTrue(command.startsWith("grep -c -F -- '"));
    }

    @Test
    @DisplayName("端口/进程采集命令只嵌入已校验的字面量")
    void businessCommandsEmbedOnlyValidatedLiterals() {
        assertEquals("ss -ltn 2>/dev/null | grep -q ':22 ' && echo 1 || echo 0",
                SentinelService.collectionCommand("business", "port:22", null));
        assertEquals("pgrep -x 'nginx' >/dev/null 2>&1 && echo 1 || echo 0",
                SentinelService.collectionCommand("business", "process:nginx", null));
        assertTrue(SentinelService.collectionCommand("business", "http:https://ops.example.test/health", null)
                .startsWith("curl -s -o /dev/null"));
    }

    @Test
    @DisplayName("未知类别不产生命令，而是明确报错")
    void unknownKindRejected() {
        assertThrows(BusinessException.class, () -> SentinelService.validateTarget("nope", "cpu"));
        assertThrows(BusinessException.class, () -> SentinelService.collectionCommand("nope", "cpu", null));
    }

    @Test
    @DisplayName("采集边界如实说明：会话级连接 → 常驻采集需要独立采集器")
    void runtimeBoundaryIsStated() {
        String note = SentinelService.runtimeBoundaryNote();
        assertTrue(note.contains("会话级"));
        assertTrue(note.contains("采集器"));
        // 不许把"做不到"说成"已实现"
        assertFalse(note.contains("7×24 已实现") || note.contains("永久在线"));
    }
}
