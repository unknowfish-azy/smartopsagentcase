package com.smartops.sentinel;

import java.util.Map;

/**
 * 断言辅助：把"不得直接执行"这条硬约束写成可复用的检查。
 *
 * <p>为什么单独抽出来：这条约束最容易在后续改动中被悄悄破坏（例如有人为了
 * "方便"在 runner 里直接调用 {@code multiExec.execute()}）。让多处测试共用
 * 同一个断言，比在每个测试里重复写字符串匹配更可靠。</p>
 */
final class SentinelExecutionPolicy {

    private SentinelExecutionPolicy() {}

    /**
     * 判断一段源码是否遵守"只预览、不执行"。
     *
     * @param source 被检查的类源码
     */
    static boolean onlyPreviews(String source) {
        // 允许出现 preview 调用；不允许出现 execute 调用
        boolean usesPreview = source.contains("multiExec.preview(");
        boolean callsExecute = source.contains("multiExec.execute(") || source.contains(".execute(");
        return usesPreview && !callsExecute;
    }

    /** 计划返回给调用方的字段里，必须明确告诉人"下一步去哪执行"。 */
    static boolean explainsNextStep(Map<String, Object> prepared) {
        Object next = prepared.get("nextStep");
        return next != null && next.toString().contains("/api/operations/multi-exec/execute");
    }
}
