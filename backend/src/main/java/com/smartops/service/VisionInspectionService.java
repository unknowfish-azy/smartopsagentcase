package com.smartops.service;

import com.smartops.assistant.VisionInspectionEngine;
import com.smartops.dto.inspector.InspectionRecordRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 视觉巡检服务：调用 {@link VisionInspectionEngine} 分析图片，
 * 并把结论按固定口径写入真实纠察事件（InspectorEventService.record 通道，
 * 内容统一经过 OperationRedactor 脱敏）。
 *
 * <p>诚实性约束：模型结论不直接判定通过——事件 status 固定 REVIEW、
 * requiresHuman 固定 true，severity 仅反映模型主张（WARN/INFO），
 * 最终处置必须由人工复核后完成。</p>
 */
@Service
public class VisionInspectionService {

    /** summary 写入事件 reason 时的截断上限。 */
    private static final int REASON_CHARS = 500;

    private final VisionInspectionEngine engine;
    private final InspectorEventService inspectorEventService;

    /**
     * sim/无模型降级时，是否强制产出 WARN 事件用于触发重规划。
     * 默认 false —— 真实联调不会被模拟干扰。
     * 由测试脚本用 smartops.robot.simulated-abnormal=true 覆盖。
     */
    private final boolean simulatedAbnormal;

    public VisionInspectionService(VisionInspectionEngine engine,
            InspectorEventService inspectorEventService,
            @Value("${smartops.robot.simulated-abnormal:false}") boolean simulatedAbnormal) {
        this.engine = engine;
        this.inspectorEventService = inspectorEventService;
        this.simulatedAbnormal = simulatedAbnormal;
    }

    /** 视觉巡检配置状态：是否已配置本地模型与模型名。 */
    public Map<String, Object> status() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("configured", engine.configured());
        result.put("model", engine.model());
        return result;
    }

    /**
     * 执行视觉识别并落一条纠察事件。
     *
     * @param imageBase64 图片 base64（纯 base64 或 data URI，由引擎统一剥前缀）
     * @param target      巡检目标（可空，默认 VISION）
     * @param filename    原始文件名（可空，写入证据 source 与 metadata）
     * @param userId      归属用户（事件按登录用户落库，可读侧过滤）
     * @return analysis（结构化结论）+ eventId / inspectionId（前端跳转纠察中心用）
     */
    public Map<String, Object> inspect(String imageBase64, String target, String filename, Long userId) {
        return inspect(imageBase64, target, filename, userId, null, null);
    }

    /**
     * 带来源标识的视觉巡检（机器人抽帧用）。
     *
     * @param taskIdPrefix    任务号前缀，如 {@code robot-robot-car-01}；为空时沿用 {@code VISION-} 口径
     * @param extraMetadata   额外追溯字段（如 {@code deviceId}），与固定字段合并写入事件 metadata
     */
    public Map<String, Object> inspect(String imageBase64, String target, String filename, Long userId,
            String taskIdPrefix, Map<String, Object> extraMetadata) {
        Boolean abnormal;
        String modelName;
        String summary;
        List<String> issues;
        String raw;

        if (simulatedAbnormal) {
            // 测试模式：无条件合成 WARN 用于触发重规划验证，绕过真实模型输出
            abnormal = true;
            modelName = "sim-abnormal";
            summary = "[SIM] 连续异常：模拟视觉模型检测到画面异常，触发机器人重规划";
            issues = List.of("模拟异常点（simulated-abnormal=true 配置）");
            raw = "simulated-abnormal=true";
        } else if (!engine.configured()) {
            // 未配置本地模型 → 诚实地降级为 INFO（不伪造异常）
            abnormal = false;
            modelName = "unconfigured";
            summary = "视觉模型未配置，跳过检测";
            issues = List.of();
            raw = "engine-not-configured";
        } else {
            VisionInspectionEngine.VisionAnalysis analysis = engine.analyze(imageBase64);
            abnormal = analysis.abnormal();
            modelName = analysis.model();
            summary = truncate(analysis.summary(), REASON_CHARS);
            issues = analysis.issues();
            raw = analysis.raw();
        }

        String trace = UUID.randomUUID().toString().replace("-", "").substring(0, 8).toUpperCase();
        InspectionRecordRequest request = new InspectionRecordRequest();
        request.setTaskId(taskIdPrefix == null || taskIdPrefix.isBlank()
                ? "VISION-" + trace
                : taskIdPrefix + "-" + trace);
        request.setTarget(target == null || target.isBlank() ? "VISION" : target.strip());
        request.setStatus("REVIEW");
        request.setSeverity(Boolean.TRUE.equals(abnormal) ? "WARN" : "INFO");
        request.setCategory("VISION");
        request.setAgentClaim("本地视觉模型 " + modelName);
        request.setReason(summary);
        request.setRecommendation("人工复核视觉识别结论后再处置");
        request.setRequiresHuman(true);
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("model", modelName);
        metadata.put("filename", filename == null ? "" : filename);
        metadata.put("abnormal", abnormal == null ? "UNKNOWN" : abnormal);
        metadata.put("simulated", !engine.configured());
        if (extraMetadata != null) {
            extraMetadata.forEach((key, value) -> {
                if (key != null && value != null) {
                    metadata.put(key, value);
                }
            });
        }
        request.setMetadata(metadata);

        InspectionRecordRequest.Evidence evidence = new InspectionRecordRequest.Evidence();
        evidence.setContent(raw);
        evidence.setSource("vision:" + (filename == null || filename.isBlank() ? "image" : filename));
        request.setEvidence(new ArrayList<>(List.of(evidence)));

        Map<String, Object> event = inspectorEventService.record(request, userId);

        Map<String, Object> analysisView = new LinkedHashMap<>();
        analysisView.put("abnormal", abnormal);
        analysisView.put("summary", summary);
        analysisView.put("issues", issues);
        analysisView.put("model", modelName);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("analysis", analysisView);
        result.put("eventId", event.get("id"));
        result.put("inspectionId", event.get("id"));
        return result;
    }

    private static String truncate(String text, int limit) {
        if (text == null) {
            return "";
        }
        int end = Math.min(text.length(), limit);
        if (end > 0 && end < text.length() && Character.isHighSurrogate(text.charAt(end - 1))) {
            end--;
        }
        return text.substring(0, end);
    }
}
