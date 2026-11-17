package com.smartops.robot;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 遥控能力清单：**唯一来源**。
 *
 * <p>前端只读 axes / maxSpeed / gaits 渲染摇杆，不判断设备类型，
 * 也不允许出现 {@code if (formFactor == "DOG")} 这类分支。
 *
 * <p>轴与 RobotCommandPolicy 的 MOVE 参数一一对应：
 * forward→x、lateral→y、yaw→theta、gait→gait。
 *
 * <p>差异必须由运动学决定，不是审美选择：
 * 差速车没有横移执行器，四足限速必须低于轮式以免失稳。
 */
public final class RobotTeleopProfiles {

    /** 未登记形态的兜底：最保守的两轴与最低限速，known=false 让前端如实提示。 */
    private static final Map<String, Object> UNKNOWN = unknown();

    private static final Map<String, Map<String, Object>> PROFILES = build();

    private RobotTeleopProfiles() {
    }

    /** 按形态取能力清单；未登记形态返回保守兜底（不抛异常，台账允许历史脏值）。 */
    public static Map<String, Object> forFormFactor(String formFactor) {
        String key = formFactor == null ? "" : formFactor.trim().toUpperCase();
        Map<String, Object> profile = PROFILES.get(key);
        return profile != null ? profile : UNKNOWN;
    }

    private static Map<String, Map<String, Object>> build() {
        Map<String, Map<String, Object>> map = new LinkedHashMap<>();
        map.put("CAR", profile("CAR", "巡逻车", "differential",
                List.of("forward", "yaw"), 0.6, 0.85, List.of(),
                "差速：前进 + 自转，无横移执行器"));
        map.put("DOG", profile("DOG", "机器狗", "quadruped",
                List.of("forward", "lateral", "yaw", "gait"), 0.35, 0.7,
                List.of("TROT", "WALK", "STAND"),
                "四足：可横移，限速低于轮式以免失稳"));
        map.put("SPIDER", profile("SPIDER", "蜘蛛机器人", "omnidirectional",
                List.of("forward", "lateral", "yaw"), 0.45, 0.8, List.of(),
                "全向：三轴独立，可原地横移"));
        map.put("ROBOT", profile("ROBOT", "巡检机器人", "differential",
                List.of("forward", "yaw"), 0.5, 0.8, List.of(),
                "通用形态：保守按差速处理"));
        return Map.copyOf(map);
    }

    private static Map<String, Object> profile(String formFactor, String label, String kinematics,
            List<String> axes, double linear, double angular, List<String> gaits, String note) {
        Map<String, Object> profile = new LinkedHashMap<>();
        profile.put("formFactor", formFactor);
        profile.put("label", label);
        profile.put("kinematics", kinematics);
        profile.put("axes", axes);
        profile.put("maxSpeed", Map.of("linear", linear, "angular", angular));
        profile.put("gaits", gaits);
        profile.put("maxSpeedNote", note);
        profile.put("known", true);
        return Map.copyOf(profile);
    }

    private static Map<String, Object> unknown() {
        Map<String, Object> profile = new LinkedHashMap<>();
        profile.put("formFactor", "UNKNOWN");
        profile.put("label", "未知形态");
        profile.put("kinematics", "differential");
        profile.put("axes", List.of("forward", "yaw"));
        profile.put("maxSpeed", Map.of("linear", 0.3, "angular", 0.5));
        profile.put("gaits", List.of());
        profile.put("maxSpeedNote", "形态未登记：按差速最低限速运行");
        profile.put("known", false);
        return Map.copyOf(profile);
    }
}
