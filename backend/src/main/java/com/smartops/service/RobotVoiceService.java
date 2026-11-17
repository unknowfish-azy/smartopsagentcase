package com.smartops.service;

import com.smartops.exception.BusinessException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 语音指令服务（M3）。
 *
 * <p>链路：语音转写文本 → 注入检测（HIGH 拦截）→ 词表匹配 → 转控制命令。
 * 不匹配任何词表 → 返回 {@code matched=false} 让前端提示「未识别指令」。</p>
 */
@Slf4j
@Service
public class RobotVoiceService {

    private final RobotControlService control;
    private final RobotBrainService brain;

    /** Prompt 注入检测（精简版，与 Python {@code safety/injection.py} 规则一致但仅覆盖高危）。 */
    private static final List<Pattern> INJECTION_PATTERNS = List.of(
            Pattern.compile("忽略(之前|以上|前面)(的)?(所有)?(指令|提示|规则)", Pattern.CASE_INSENSITIVE),
            Pattern.compile("ignore\\s+(all\\s+)?(previous|prior|above)\\s+instructions?", Pattern.CASE_INSENSITIVE),
            Pattern.compile("system\\s*prompt|你的?真实?指令|reveal\\s+your\\s+(instructions|prompt)", Pattern.CASE_INSENSITIVE),
            Pattern.compile("(你现在是|假装你是|从现在开始你是|扮演)(一个)?(没有限制|不受约束|任意|DAN|开发者模式)", Pattern.CASE_INSENSITIVE),
            Pattern.compile("(输出|打印|泄露|告诉我)(你的)?(系统提示|密钥|api\\s*key|配置)", Pattern.CASE_INSENSITIVE));

    public RobotVoiceService(RobotControlService control, RobotBrainService brain) {
        this.control = control;
        this.brain = brain;
    }

    public Map<String, Object> handle(String deviceKey, String text, String operator) {
        if (text == null || text.isBlank()) {
            throw new BusinessException(400, "语音文本不能为空");
        }
        String sanitized = text.strip();
        Map<String, Object> scan = scan(sanitized);
        if (Boolean.TRUE.equals(scan.get("blocked"))) {
            // 注入命中：仅审计一次拦截，不执行任何命令
            log.warn("语音注入拦截 [device={} operator={}] text={}", deviceKey, operator, sanitized);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("matched", false);
            result.put("blocked", true);
            result.put("scan", scan);
            result.put("message", "指令包含高危注入话术，已拒绝执行");
            return result;
        }

        String lower = sanitized.toLowerCase();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("matched", false);
        result.put("blocked", false);
        result.put("scan", scan);

        if (any(lower, "停止", "停下来", "停下", "stop", "halt")) {
            result.put("matched", true);
            result.put("op", "STOP");
            try {
                result.put("execution", control.emergencyStop(deviceKey, operator));
            } catch (BusinessException e) {
                result.put("executionError", e.getMessage());
            }
            return result;
        }
        if (any(lower, "拍照", "拍一张", "抓一张", "capture", "snapshot")) {
            result.put("matched", true);
            result.put("op", "CAPTURE");
            try {
                result.put("execution", control.command(
                        deviceKey, "CONSOLE", "CAPTURE", Map.of("target", sanitized), operator));
            } catch (BusinessException e) {
                result.put("executionError", e.getMessage());
            }
            return result;
        }
        if (any(lower, "开始巡检", "开始巡逻", "出发巡检", "开始自主", "start patrol", "start inspection")) {
            result.put("matched", true);
            result.put("op", "PATROL");
            try {
                result.put("execution", brain.submit(deviceKey, defaultRoute(), null, operator));
            } catch (BusinessException e) {
                result.put("executionError", e.getMessage());
            }
            return result;
        }
        if (any(lower, "暂停任务", "暂停巡检", "pause")) {
            result.put("matched", true);
            result.put("op", "PAUSE_LATEST");
            Long taskId = latestTaskId(deviceKey);
            if (taskId != null) {
                try {
                    result.put("execution", brain.pause(taskId, operator));
                } catch (BusinessException e) {
                    result.put("executionError", e.getMessage());
                }
            } else {
                result.put("message", "无进行中任务");
            }
            return result;
        }
        if (any(lower, "取消任务", "停止任务", "cancel task")) {
            result.put("matched", true);
            result.put("op", "CANCEL_LATEST");
            Long taskId = latestTaskId(deviceKey);
            if (taskId != null) {
                try {
                    result.put("execution", brain.cancel(taskId, operator));
                } catch (BusinessException e) {
                    result.put("executionError", e.getMessage());
                }
            } else {
                result.put("message", "无进行中任务");
            }
            return result;
        }

        result.put("message", "未识别指令（支持：停止、拍照、开始巡检、暂停任务、取消任务）");
        return result;
    }

    private boolean any(String lower, String... keywords) {
        for (String kw : keywords) {
            if (lower.contains(kw.toLowerCase())) {
                return true;
            }
        }
        return false;
    }

    /** 精简注入检测：命中任一高危 pattern → blocked=true。 */
    private Map<String, Object> scan(String text) {
        Map<String, Object> result = new LinkedHashMap<>();
        java.util.List<String> matched = new java.util.ArrayList<>();
        for (Pattern p : INJECTION_PATTERNS) {
            if (p.matcher(text).find()) {
                matched.add(p.pattern());
            }
        }
        result.put("matchedRules", matched);
        result.put("blocked", !matched.isEmpty());
        return result;
    }

    private java.util.List<Map<String, Object>> defaultRoute() {
        java.util.List<Map<String, Object>> route = new java.util.ArrayList<>();
        for (double theta : new double[]{0, 90, 180, 270}) {
            Map<String, Object> point = new LinkedHashMap<>();
            point.put("x", theta == 0 || theta == 270 ? 0.0 : 3.0);
            point.put("y", theta == 0 || theta == 90 ? 0.0 : 3.0);
            point.put("theta", theta);
            point.put("label", "语音触发-路点");
            point.put("actions", List.of("CAPTURE"));
            route.add(point);
        }
        return route;
    }

    private Long latestTaskId(String deviceKey) {
        try {
            List<Map<String, Object>> list = brain.list(deviceKey);
            for (Map<String, Object> t : list) {
                String status = String.valueOf(t.get("status"));
                if ("RUNNING".equals(status) || "PAUSED".equals(status)) {
                    return ((Number) t.get("id")).longValue();
                }
            }
        } catch (Exception ignored) {
        }
        return null;
    }
}
