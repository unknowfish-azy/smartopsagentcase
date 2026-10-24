package com.smartops.sentinel;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 执行链路的**结构性约束**测试：直接读源码断言"没有第二条执行通路"。
 *
 * <p>这类测试看起来粗暴，但它防的是最危险的一类回退：某次改动为了让
 * 定时/告警模式"更顺手"，在 runner 里直接调用了执行接口。业务测试很难发现，
 * 而这条断言会立刻失败。</p>
 */
class SentinelScriptRunnerPolicyTest {

    private static String source(String className) throws Exception {
        // 测试运行时工作目录是 backend/，源码在 src/main/java 下
        Path path = Path.of("src/main/java/com/smartops/sentinel/" + className + ".java");
        return Files.readString(path, StandardCharsets.UTF_8);
    }

    @Test
    @DisplayName("脚本执行编排只生成预览，绝不直接执行")
    void runnerOnlyPreviewsNeverExecutes() throws Exception {
        String runner = source("SentinelScriptRunner");
        assertTrue(runner.contains("multiExec.preview("), "必须经既有预览接口");
        assertFalse(runner.contains("multiExec.execute("), "不得调用执行接口");
        // 也不允许自己拼一条新的执行路径（写终端/发命令）
        assertFalse(runner.contains(".write("), "不得直接向运行连接写命令");
        assertFalse(runner.contains("/multi-exec/execute\""), "不得在代码里内联执行 URL");
    }

    @Test
    @DisplayName("三种触发模式共用同一个准备入口，不存在第三种旁路")
    void singlePreparationEntryPoint() throws Exception {
        String runner = source("SentinelScriptRunner");
        // 只应有一个 prepare 方法（public），避免"定时专用执行""告警专用执行"各自长出来
        int prepareCount = count(runner, "Map<String, Object> prepare(");
        assertTrue(prepareCount == 1, "只能有一个 prepare 入口，实际发现 " + prepareCount);
        assertTrue(runner.contains("TRIGGER_MANUAL") && runner.contains("TRIGGER_SCHEDULE") && runner.contains("TRIGGER_ALERT"));
    }

    @Test
    @DisplayName("执行记录先落 PENDING_APPROVAL，不会写成已成功")
    void recordsPendingNotSuccess() throws Exception {
        String runner = source("SentinelScriptRunner");
        assertTrue(runner.contains("\"PENDING_APPROVAL\""), "必须登记为待审批");
        assertFalse(runner.contains("\"SUCCESS\""), "不得在编排阶段写成功状态");
        assertFalse(runner.contains("\"success\""), "不得在编排阶段写成功状态");
    }

    @Test
    @DisplayName("P0/P1 与高危脚本一律要求人工确认")
    void humanApprovalGateIsPresent() throws Exception {
        String runner = source("SentinelScriptRunner");
        assertTrue(runner.contains("requiresApproval(script.riskLevel())"));
        assertTrue(runner.contains("\"P0\".equals(severity)") && runner.contains("\"P1\".equals(severity)"));
        assertTrue(runner.contains("humanApprovalRequired"));
    }

    private static int count(String text, String needle) {
        int total = 0;
        int index = text.indexOf(needle);
        while (index >= 0) {
            total++;
            index = text.indexOf(needle, index + needle.length());
        }
        return total;
    }
}
