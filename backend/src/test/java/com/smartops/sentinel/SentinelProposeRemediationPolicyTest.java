package com.smartops.sentinel;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 协作优化 4 的结构性约束：告警处置接进团队审批链，但**不是**新执行通路。
 *
 * <p>这类测试读源码断言，防的是最危险的回退：有人为了"让告警自动处置更顺畅"，
 * 在 propose 里直接调用执行接口。业务测试很难发现，这条断言会立刻失败。</p>
 */
class SentinelProposeRemediationPolicyTest {

    private static String source(String relative) throws Exception {
        return Files.readString(Path.of("src/main/java/com/smartops/" + relative), StandardCharsets.UTF_8);
    }

    @Test
    @DisplayName("propose 只创建待审批运行，不执行命令")
    void proposeCreatesPendingRunOnly() throws Exception {
        String runner = source("sentinel/SentinelScriptRunner.java");
        // 必须生成既有链路预览
        assertTrue(runner.contains("multiExec.preview("), "必须经既有预览接口");
        // 必须创建团队待审批运行（体现"复用 TeamAgentRun"）
        assertTrue(runner.contains("teamRuns.create("), "必须复用团队运行创建");
        // 不得执行
        assertFalse(runner.contains("multiExec.execute("), "不得调用执行接口");
        assertFalse(runner.contains("executeApprovedTeamRun"), "不得走通用执行入口");
        assertFalse(runner.contains(".write("), "不得直接向运行连接写命令");
    }

    @Test
    @DisplayName("提议返回的下一步指向审批链，而不是声称已执行")
    void proposeExplainsApprovalPath() throws Exception {
        String runner = source("sentinel/SentinelScriptRunner.java");
        assertTrue(runner.contains("preview 后 approve"), "必须说明要先预览再审批");
        assertTrue(runner.contains("哨兵不直接执行命令"), "必须明确不执行");
        // 结果里不能出现表示"已完成执行"的措辞
        assertFalse(runner.contains("\"status\", \"SUCCEEDED\""), "提议阶段不得声称执行成功");
    }

    @Test
    @DisplayName("通用执行入口拒绝执行 propose-remediation")
    void genericExecutorRejectsProposalTool() throws Exception {
        String tools = source("service/OperationToolService.java");
        // 注册为非只读 → TeamAgentRun 会进入 PENDING_APPROVAL
        // 目录构造器在 OPS-01 中统一为 readOnly/mutating 两类；
        // `mutating(...)` 保证 readOnly=false，约束与原先等价，只是写法收敛。
        assertTrue(tools.contains("mutating(\"propose-remediation\""),
                "必须是非只读工具，才会进入待审批");
        // 且不允许从通用执行入口直接跑掉
        assertTrue(tools.contains("TEAM_REMEDIATION_REQUIRES_SENTINEL_PREVIEW"),
                "通用执行入口必须拒绝该工具");
    }

    @Test
    @DisplayName("提议用到的变量同样经过注入校验")
    void proposeAppliesCheckedVariables() throws Exception {
        String runner = source("sentinel/SentinelScriptRunner.java");
        assertTrue(runner.contains("SentinelVariables.applyChecked("),
                "提议路径也必须用带校验的变量替换");
        assertTrue(runner.contains("SentinelScriptLint.lint("),
                "提议路径也必须过一遍高危预检");
    }
}
