package com.smartops.dto.robot;

import lombok.Data;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 巡检机器人设备登记/更新请求（M0 设备台账）。
 *
 * <p>格式校验集中在 {@code RobotRegistryService}（白名单集中校验原则），
 * 注解仅做非空兜底；transport 仅接受固定键集合，未知键直接拒绝。</p>
 */
@Data
public class RobotDeviceUpsertRequest {

    private String deviceKey;

    private String name;

    /** CAR / SPIDER / DOG / ROBOT */
    private String formFactor;

    /** MOVE/PTZ/MIC/SPEAKER/CAMERA/LIDAR 子集 */
    private List<String> capabilities = new ArrayList<>();

    /** {"type":"BLE","mac":"AA:BB:CC:DD:EE:FF","protocolId":"generic-ble-car-v1"} */
    private Map<String, Object> transport = new LinkedHashMap<>();

    private String firmware;
}
