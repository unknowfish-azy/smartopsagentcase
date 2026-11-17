package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.robot.RobotTelemetryHub;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * 机器人视觉巡检闭环（M2）。
 *
 * <p>职责：
 * <ol>
 *   <li>缓存每个设备的最新关键帧（不含原始视频流，帧率由桥侧节流）；</li>
 *   <li>仅在显式 {@code CAPTURE} 意图存在时触发视觉巡检，避免每一帧都消耗本地模型；</li>
 *   <li>巡检在独立线程执行：桥 WS 线程必须保持空转，否则遥测停发会被心跳看门狗误判 FAULT；</li>
 *   <li>结论经 {@link VisionInspectionService} 落真实纠察事件（status=REVIEW、requiresHuman=true），
 *       并把结果广播给控制台供人工复核。</li>
 * </ol>
 * 视觉模型未配置时如实降级为 {@code VISION_UNAVAILABLE} 广播，不抛出、不阻塞遥控。</p>
 */
@Slf4j
@Service
public class RobotFrameService {

    /** 拍照意图有效期：超时后到达的帧按普通帧处理，避免迟到的旧意图误触发模型。 */
    private static final long INTENT_TTL_MS = 30_000;

    private final VisionInspectionService visionService;
    private final RobotTelemetryHub hub;
    private final long minInspectIntervalMs;
    private final ExecutorService executor = Executors.newFixedThreadPool(2, runnable -> {
        Thread thread = new Thread(runnable, "robot-vision");
        thread.setDaemon(true);
        return thread;
    });

    /** deviceKey → 最新关键帧（imageBase64/quality/receivedAt）。 */
    private final Map<String, Map<String, Object>> latestFrames = new ConcurrentHashMap<>();
    /** deviceKey → 最近一次视觉巡检结果（供 REST 首屏回填）。 */
    private final Map<String, Map<String, Object>> lastAnalyses = new ConcurrentHashMap<>();
    /** deviceKey → 拍照意图（target + 过期时间）。 */
    private final Map<String, CaptureIntent> intents = new ConcurrentHashMap<>();
    /** deviceKey → 最近一次触发模型的时间戳，防止连续点击打爆本地模型。 */
    private final Map<String, Long> lastInspectAt = new ConcurrentHashMap<>();

    public RobotFrameService(VisionInspectionService visionService,
            RobotTelemetryHub hub,
            @Value("${smartops.robot.frame-interval-ms:2000}") long minInspectIntervalMs) {
        this.visionService = visionService;
        this.hub = hub;
        this.minInspectIntervalMs = minInspectIntervalMs;
    }

    /** 命令下发成功（CAPTURE）后登记意图：随后到达的帧触发一次视觉巡检。 */
    public void expectCapture(String deviceKey, String target) {
        intents.put(deviceKey, new CaptureIntent(target, System.currentTimeMillis() + INTENT_TTL_MS));
    }

    /**
     * 桥上报关键帧：更新最新帧快照；若存在有效拍照意图则异步触发视觉巡检。
     *
     * @param payload 桥上报内容（含 imageBase64，可含 quality/width/height）
     */
    public void accept(String deviceKey, Map<String, Object> payload) {
        String imageBase64 = payload.get("imageBase64") == null ? "" : String.valueOf(payload.get("imageBase64"));
        if (imageBase64.isBlank()) {
            return;
        }
        Map<String, Object> frame = new LinkedHashMap<>();
        frame.put("deviceKey", deviceKey);
        frame.put("imageBase64", imageBase64);
        frame.put("mime", payload.get("mime"));
        frame.put("simulated", payload.get("simulated"));
        frame.put("quality", payload.get("quality"));
        frame.put("receivedAt", Instant.now().toString());
        latestFrames.put(deviceKey, frame);

        CaptureIntent intent = intents.remove(deviceKey);
        if (intent == null || intent.expiresAt() < System.currentTimeMillis()) {
            return; // 普通帧：只缓存供控制台查看，不消耗本地模型
        }
        long now = System.currentTimeMillis();
        Long previous = lastInspectAt.get(deviceKey);
        if (previous != null && now - previous < minInspectIntervalMs) {
            broadcastVision(deviceKey, intent, Map.of(
                    "status", "THROTTLED",
                    "message", "视觉巡检触发过于频繁，本次帧仅缓存（最小间隔 "
                            + minInspectIntervalMs + "ms）"));
            return;
        }
        lastInspectAt.put(deviceKey, now);
        submit(deviceKey, intent, imageBase64);
    }

    /** 最新关键帧；无帧返回 null（不伪造画面）。 */
    public Map<String, Object> latestFrame(String deviceKey) {
        Map<String, Object> frame = latestFrames.get(deviceKey);
        if (frame == null) {
            return null;
        }
        Map<String, Object> view = new LinkedHashMap<>(frame);
        view.put("lastAnalysis", lastAnalyses.get(deviceKey));
        return view;
    }

    /** 视觉巡检配置状态（控制台据此显示「已配置/未配置」）。 */
    public Map<String, Object> visionStatus() {
        return visionService.status();
    }

    private void submit(String deviceKey, CaptureIntent intent, String imageBase64) {
        executor.submit(() -> {
            try {
                Map<String, Object> result = visionService.inspect(
                        imageBase64,
                        intent.target(),
                        "robot-" + deviceKey + ".jpg",
                        null,
                        "robot-" + deviceKey,
                        Map.of("deviceId", deviceKey));
                Map<String, Object> payload = new LinkedHashMap<>(result);
                payload.put("status", "OK");
                lastAnalyses.put(deviceKey, payload);
                broadcastVision(deviceKey, intent, payload);
            } catch (BusinessException e) {
                // 视觉模型未配置/不可用：如实上报，遥控与遥测不受影响
                Map<String, Object> payload = new LinkedHashMap<>();
                payload.put("status", e.getCode() == 503 ? "VISION_UNAVAILABLE" : "FAILED");
                payload.put("code", e.getCode());
                payload.put("message", e.getMessage());
                lastAnalyses.put(deviceKey, payload);
                broadcastVision(deviceKey, intent, payload);
            } catch (RuntimeException e) {
                log.warn("机器人 {} 视觉巡检失败：{}", deviceKey, e.getMessage());
                Map<String, Object> payload = new LinkedHashMap<>();
                payload.put("status", "FAILED");
                payload.put("message", "视觉巡检执行失败");
                lastAnalyses.put(deviceKey, payload);
                broadcastVision(deviceKey, intent, payload);
            }
        });
    }

    private void broadcastVision(String deviceKey, CaptureIntent intent, Map<String, Object> payload) {
        Map<String, Object> message = new LinkedHashMap<>(payload);
        message.put("deviceKey", deviceKey);
        message.put("target", intent.target());
        hub.broadcast("vision", message);
    }

    @PreDestroy
    void shutdown() {
        executor.shutdownNow();
        try {
            executor.awaitTermination(2, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /** 拍照意图：目标标签 + 过期时间戳。 */
    private record CaptureIntent(String target, long expiresAt) { }
}
