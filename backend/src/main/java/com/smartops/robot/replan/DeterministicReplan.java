package com.smartops.robot.replan;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 确定性重规划（M6 默认策略，真机不可用时始终可靠）。
 *
 * <p>算法：
 * <ol>
 *   <li>找到当前触发重规划的路点（anomalyIndex = currentIndex）；</li>
 *   <li>在其位置生成一个绕行点：{x+2, y+2}（对角线方向，CAR 差速器形态能横向斜走）；</li>
 *   <li>保持当前点索引不变 → 由 RobotBrainService 的 while 循环 continue 原地执行。</li>
 * </ol>
 *
 * <p>简单但有效：真机接入时只要 obstacle sensor 能提供障碍物坐标，
 * 可把 (x+2, y+2) 替换为 (nearestClearX, nearestClearY) 基于真实障碍图绕行。</p>
 */
@Component
public class DeterministicReplan implements ReplanStrategy {

    @Override public String name() { return "deterministic"; }

    @Override
    public ReplanResult replan(List<Map<String, Object>> route, int currentIndex, String deviceKey) {
        long start = System.currentTimeMillis();
        try {
            List<Map<String, Object>> newRoute = new ArrayList<>(route);
            Map<String, Object> current = newRoute.get(currentIndex);
            double cx = num(current.get("x"));
            double cy = num(current.get("y"));
            double theta = num(current.get("theta"));

            Map<String, Object> detour = new LinkedHashMap<>();
            detour.put("x", cx + 2.0);
            detour.put("y", cy + 2.0);
            detour.put("theta", theta);
            detour.put("label", "绕行-" + deviceKey + "-" + (System.currentTimeMillis() % 1000));
            detour.put("actions", List.of("CAPTURE"));
            newRoute.set(currentIndex, detour);

            return new SuccessResult(newRoute, name(), System.currentTimeMillis() - start);
        } catch (Exception e) {
            return FallbackResult.fallback("deterministic replan 异常：" + e.getMessage());
        }
    }

    private static double num(Object v) {
        if (v == null) return 0.0;
        if (v instanceof Number n) return n.doubleValue();
        try { return Double.parseDouble(String.valueOf(v)); } catch (NumberFormatException ex) { return 0.0; }
    }
}
