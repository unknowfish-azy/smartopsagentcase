package com.smartops.robot.replan;

import java.util.List;
import java.util.Map;

/**
 * 机器人重规划策略 —— M7 抽象层。
 *
 * <p>M6 引入后，重规划触发条件（连续 WARN/CRITICAL）与执行器（RobotBrainService.while 循环）
 * 已独立；M7 将"怎么生成绕行点"抽象为策略，真机接入时可替换为：
 * <ul>
 *   <li>基于 obstacle sensor 的启发式绕行（多形态物理模型）；</li>
 *   <li>调用本地/远端 LLM planner 的 JSON route 生成；</li>
 *   <li>Agent DAG planner 工具链（后端 HTTP 调 agent tool endpoint）。</li>
 * </ul>
 *
 * <p>Fail-closed：任何策略异常必须返回 {@link FallbackResult#fallback()}，
 * 由调用方继续执行兜底（通常是 x+2/y+2 确定性绕行），绝不阻塞任务。</p>
 */
public interface ReplanStrategy {

    /** 策略标识（日志/trace 用）。 */
    String name();

    /**
     * 尝试重规划。
     *
     * @param route        当前完整 route（不可变）
     * @param currentIndex 当前触发重规划的路点索引
     * @param deviceKey    设备 key（用于标签前缀）
     * @return 重规划结果 —— 可能成功（{@link ReplanResult#success(List, String, String)}）
     *                      或请求兜底（{@link FallbackResult}）
     */
    ReplanResult replan(List<Map<String, Object>> route, int currentIndex, String deviceKey);

    // ------------------------------------------------------------------
    // result 类型
    // ------------------------------------------------------------------

    /** 重规划结果基类。 */
    sealed interface ReplanResult permits SuccessResult, FallbackResult {

        /** 是否请求 fallback（策略不可用/超时/解析失败）。 */
        boolean isFallback();

        /** 策略耗时（毫秒），日志/trace 用。 */
        long elapsedMs();
    }

    /** 成功生成了新 route。 */
    record SuccessResult(List<Map<String, Object>> newRoute, String routeSource, long elapsedMs)
            implements ReplanResult {
        @Override public boolean isFallback() { return false; }
    }

    /** 请求兜底（策略异常/不可用）。 */
    record FallbackResult(String reason, long elapsedMs) implements ReplanResult {
        @Override public boolean isFallback() { return true; }

        /** 便捷构造：统一兜底入口。 */
        static FallbackResult fallback(String reason) {
            return new FallbackResult(reason, 0L);
        }
    }
}
