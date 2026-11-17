package com.smartops.robot;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 巡检机器人命令白名单与参数钳位（集中校验，类比 OutboundUrlPolicy）。
 *
 * <p>任何来源（人工态前端、自主态大脑、内部接口）下发的命令都必须先经过本类，
 * 校验失败抛 {@link RobotPolicyViolation}，仅携带规则码，不回显目标细节。
 * 未知 op 一律拒绝（fail-closed），不做「宽松兜底」。</p>
 */
public final class RobotCommandPolicy {

    /** 允许的命令操作。 */
    public static final Set<String> OPS = Set.of("MOVE", "PTZ", "SPEAK", "CAPTURE", "PATROL", "STOP");

    /** MOVE 的 ttlMs 上限：dead-man switch，松开摇杆后必须自动停。 */
    public static final int MAX_TTL_MS = 500;
    public static final int MIN_TTL_MS = 50;
    /** SPEAK 文本长度上限（喊话）。 */
    public static final int MAX_SPEAK_CHARS = 200;
    /** PATROL 路点数上限。 */
    public static final int MAX_ROUTE_POINTS = 50;
    /** 四足步态白名单：仅 MOVE 可携带，其它形态不传即不下发。 */
    public static final Set<String> GAITS = Set.of("TROT", "WALK", "STAND");
    /** 单设备每秒命令数上限（前端摇杆节流 80ms ≈ 12.5/s，留余量）。 */
    public static final int MAX_COMMANDS_PER_SECOND = 20;

    private RobotCommandPolicy() {
    }

    /** 策略违规：携带稳定规则码，前端据此提示，不泄露内部实现。 */
    public static final class RobotPolicyViolation extends RuntimeException {
        private final String code;

        public RobotPolicyViolation(String code, String message) {
            super(message);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    /**
     * 校验并归一化命令，返回可直接下发给桥的参数副本（不修改入参）。
     *
     * @param op     操作类型
     * @param params 原始参数（可为 null，STOP 无需参数）
     */
    public static Map<String, Object> normalize(String op, Map<String, Object> params) {
        String normalizedOp = op == null ? "" : op.strip().toUpperCase();
        if (!OPS.contains(normalizedOp)) {
            throw new RobotPolicyViolation("ROBOT_OP_NOT_ALLOWED", "不支持的机器人操作：" + op);
        }
        Map<String, Object> source = params == null ? Map.of() : params;
        Map<String, Object> out = new LinkedHashMap<>();
        switch (normalizedOp) {
            case "MOVE" -> normalizeMove(source, out);
            case "PTZ" -> normalizePtz(source, out);
            case "SPEAK" -> normalizeSpeak(source, out);
            case "CAPTURE" -> normalizeCapture(source, out);
            case "PATROL" -> normalizePatrol(source, out);
            default -> { /* STOP 无参数 */ }
        }
        return out;
    }

    private static void normalizeMove(Map<String, Object> source, Map<String, Object> out) {
        out.put("x", unit(source.get("x"), "ROBOT_PARAM_OUT_OF_RANGE"));
        out.put("y", unit(source.get("y"), "ROBOT_PARAM_OUT_OF_RANGE"));
        out.put("theta", unit(source.get("theta"), "ROBOT_PARAM_OUT_OF_RANGE"));
        double speed = number(source.get("speed"), 0.5, "ROBOT_PARAM_OUT_OF_RANGE");
        if (speed < 0 || speed > 1) {
            throw new RobotPolicyViolation("ROBOT_PARAM_OUT_OF_RANGE", "speed 必须在 0~1 之间");
        }
        out.put("speed", speed);
        int ttl = (int) number(source.get("ttlMs"), 200, "ROBOT_PARAM_OUT_OF_RANGE");
        if (ttl < MIN_TTL_MS || ttl > MAX_TTL_MS) {
            throw new RobotPolicyViolation("ROBOT_PARAM_OUT_OF_RANGE",
                    "ttlMs 必须在 " + MIN_TTL_MS + "~" + MAX_TTL_MS + " 之间");
        }
        out.put("ttlMs", ttl);
        // 可选步态：未传即不下发（轮式设备不携带该字段）
        Object rawGait = source.get("gait");
        if (rawGait != null && !String.valueOf(rawGait).isBlank()) {
            String gait = String.valueOf(rawGait).strip().toUpperCase();
            if (!GAITS.contains(gait)) {
                throw new RobotPolicyViolation("ROBOT_PARAM_INVALID", "步态仅允许 TROT/WALK/STAND");
            }
            out.put("gait", gait);
        }
    }

    private static void normalizePtz(Map<String, Object> source, Map<String, Object> out) {
        double pan = number(source.get("pan"), 0, "ROBOT_PARAM_OUT_OF_RANGE");
        double tilt = number(source.get("tilt"), 0, "ROBOT_PARAM_OUT_OF_RANGE");
        if (pan < -180 || pan > 180 || tilt < -90 || tilt > 90) {
            throw new RobotPolicyViolation("ROBOT_PARAM_OUT_OF_RANGE", "PTZ 角度越界");
        }
        out.put("pan", pan);
        out.put("tilt", tilt);
    }

    private static void normalizeSpeak(Map<String, Object> source, Map<String, Object> out) {
        Object raw = source.get("text");
        String text = raw == null ? "" : String.valueOf(raw).strip();
        if (text.isEmpty()) {
            throw new RobotPolicyViolation("ROBOT_PARAM_INVALID", "喊话内容不能为空");
        }
        // 控制字符会破坏设备侧指令分帧，直接拒绝而不是静默清洗
        if (text.chars().anyMatch(Character::isISOControl)) {
            throw new RobotPolicyViolation("ROBOT_PARAM_INVALID", "喊话内容不能包含控制字符");
        }
        if (text.length() > MAX_SPEAK_CHARS) {
            throw new RobotPolicyViolation("ROBOT_PARAM_OUT_OF_RANGE",
                    "喊话内容不能超过 " + MAX_SPEAK_CHARS + " 字");
        }
        out.put("text", text);
    }

    private static void normalizeCapture(Map<String, Object> source, Map<String, Object> out) {
        Object raw = source.get("target");
        String target = raw == null ? "" : String.valueOf(raw).strip();
        if (target.length() > 128 || target.chars().anyMatch(Character::isISOControl)) {
            throw new RobotPolicyViolation("ROBOT_PARAM_INVALID", "拍照目标标签非法");
        }
        out.put("target", target);
    }

    @SuppressWarnings("unchecked")
    private static void normalizePatrol(Map<String, Object> source, Map<String, Object> out) {
        Object raw = source.get("route");
        if (!(raw instanceof List<?> route) || route.isEmpty()) {
            throw new RobotPolicyViolation("ROBOT_PARAM_INVALID", "巡检路线不能为空");
        }
        if (route.size() > MAX_ROUTE_POINTS) {
            throw new RobotPolicyViolation("ROBOT_PARAM_OUT_OF_RANGE",
                    "巡检路点不能超过 " + MAX_ROUTE_POINTS + " 个");
        }
        List<Map<String, Object>> points = new java.util.ArrayList<>();
        for (Object item : route) {
            if (!(item instanceof Map<?, ?> point)) {
                throw new RobotPolicyViolation("ROBOT_PARAM_INVALID", "路点必须是对象");
            }
            Map<String, Object> normalized = new LinkedHashMap<>();
            normalized.put("x", number(point.get("x"), 0, "ROBOT_PARAM_OUT_OF_RANGE"));
            normalized.put("y", number(point.get("y"), 0, "ROBOT_PARAM_OUT_OF_RANGE"));
            Object actions = point.get("actions");
            normalized.put("actions", actions instanceof List<?> list
                    ? list.stream().map(v -> String.valueOf(v).strip().toUpperCase()).toList()
                    : List.of("CAPTURE"));
            points.add(normalized);
        }
        out.put("route", points);
    }

    /** 归一化到 [-1,1] 的摇杆量。 */
    private static double unit(Object raw, String code) {
        double value = number(raw, 0, code);
        if (value < -1 || value > 1) {
            throw new RobotPolicyViolation(code, "摇杆量必须在 -1~1 之间");
        }
        return value;
    }

    private static double number(Object raw, double fallback, String code) {
        if (raw == null) {
            return fallback;
        }
        if (raw instanceof Number number) {
            double value = number.doubleValue();
            if (Double.isNaN(value) || Double.isInfinite(value)) {
                throw new RobotPolicyViolation(code, "数值非法");
            }
            return value;
        }
        try {
            return Double.parseDouble(String.valueOf(raw).strip());
        } catch (NumberFormatException e) {
            throw new RobotPolicyViolation(code, "数值非法");
        }
    }
}
