package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.robot.RobotTelemetryHub;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.after;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 机器人视觉巡检闭环（M2）：帧缓存、拍照意图、节流、未配置降级。
 *
 * <p>视觉巡检在独立线程执行，因此断言使用 Mockito 的 timeout/after 等待异步结果；
 * 不依赖真实模型或真实桥。</p>
 */
class RobotFrameServiceTest {

    private static final String DEVICE = "robot-car-01";
    private static final String IMAGE = "iVBORw0KGgoAAAANSUhEUg==";

    private VisionInspectionService vision;
    private RobotTelemetryHub hub;
    private RobotFrameService frames;

    @BeforeEach
    void setUp() {
        vision = mock(VisionInspectionService.class);
        hub = mock(RobotTelemetryHub.class);
        frames = new RobotFrameService(vision, hub, 2000);
    }

    @AfterEach
    void tearDown() {
        frames.shutdown();
    }

    @Test
    void captureIntentTriggersInspectionWithTraceableMetadata() {
        when(vision.inspect(anyString(), anyString(), anyString(), isNull(), anyString(), anyMap()))
                .thenReturn(Map.of("eventId", "INS-001", "inspectionId", "INS-001"));

        frames.expectCapture(DEVICE, "配电柜 A");
        frames.accept(DEVICE, Map.of("imageBase64", IMAGE, "quality", "low"));

        verify(vision, timeout(2000)).inspect(
                IMAGE, "配电柜 A", "robot-" + DEVICE + ".jpg", null, "robot-" + DEVICE, Map.of("deviceId", DEVICE));
        verify(hub, timeout(2000)).broadcast(eq("vision"), any());
    }

    @Test
    void frameWithoutCaptureIntentIsOnlyCached() {
        frames.accept(DEVICE, Map.of("imageBase64", IMAGE));

        verify(vision, after(400).never())
                .inspect(anyString(), anyString(), anyString(), isNull(), anyString(), anyMap());
        Map<String, Object> frame = frames.latestFrame(DEVICE);
        assertThat(frame).isNotNull();
        assertThat(frame.get("imageBase64")).isEqualTo(IMAGE);
        assertThat(frame.get("lastAnalysis")).isNull();
    }

    @Test
    void secondCaptureWithinIntervalIsThrottled() {
        when(vision.inspect(anyString(), anyString(), anyString(), isNull(), anyString(), anyMap()))
                .thenReturn(Map.of("eventId", "INS-001"));

        frames.expectCapture(DEVICE, "A");
        frames.accept(DEVICE, Map.of("imageBase64", IMAGE));
        frames.expectCapture(DEVICE, "A");
        frames.accept(DEVICE, Map.of("imageBase64", IMAGE));

        verify(vision, timeout(2000)).inspect(
                anyString(), anyString(), anyString(), isNull(), anyString(), anyMap());
        verify(vision, after(300).times(1))
                .inspect(anyString(), anyString(), anyString(), isNull(), anyString(), anyMap());
    }

    @Test
    void unconfiguredVisionDegradesWithoutThrowing() {
        when(vision.inspect(anyString(), anyString(), anyString(), isNull(), anyString(), anyMap()))
                .thenThrow(new BusinessException(503, "视觉巡检未配置本地模型（VISION_MODEL_NOT_CONFIGURED）"));

        frames.expectCapture(DEVICE, "A");
        frames.accept(DEVICE, Map.of("imageBase64", IMAGE));

        verify(hub, timeout(2000)).broadcast(eq("vision"), org.mockito.ArgumentMatchers.argThat(payload ->
                "VISION_UNAVAILABLE".equals(payload.get("status"))));
        assertThat(frames.latestFrame(DEVICE).get("lastAnalysis")).isNotNull();
    }

    @Test
    void blankFrameIsIgnored() {
        frames.expectCapture(DEVICE, "A");
        frames.accept(DEVICE, Map.of("imageBase64", "  "));

        assertThat(frames.latestFrame(DEVICE)).isNull();
        verify(vision, after(300).never())
                .inspect(anyString(), anyString(), anyString(), isNull(), anyString(), anyMap());
    }
}
