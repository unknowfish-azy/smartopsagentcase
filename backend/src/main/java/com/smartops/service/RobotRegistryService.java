package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.robot.RobotDeviceUpsertRequest;
import com.smartops.exception.BusinessException;
import com.smartops.robot.RobotTelemetryHub;
import com.smartops.robot.RobotTeleopProfiles;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * 巡检机器人设备台账（M0）。
 *
 * <p>fail-closed 原则：新设备默认 {@code enabled=0}，未启用不可控制；
 * 校验集中在本类（白名单 + 格式钳位），拒绝时不回显内部细节之外的信息。
 * 遥测为内存快照（M1 引入 TelemetryHub），此处状态与 last_seen 仅由显式更新维护。</p>
 */
@Service
public class RobotRegistryService {

    /** 设备业务主键格式：小写字母数字与连字符，2-64 位。 */
    private static final Pattern DEVICE_KEY = Pattern.compile("^[a-z0-9][a-z0-9-]{1,63}$");
    /** MAC 地址（冒号分隔）。 */
    private static final Pattern MAC = Pattern.compile("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$");
    /** 协议适配器 ID 格式。 */
    private static final Pattern PROTOCOL_ID = Pattern.compile("^[a-z0-9][a-z0-9_-]{1,63}$");
    /** 固件版本号安全字符集。 */
    private static final Pattern FIRMWARE = Pattern.compile("^[a-zA-Z0-9._+~-]{1,64}$");

    /** M0 仅支持蓝牙直连设备；WiFi/SDK 型在 M4 按真机型号扩展。 */
    private static final Set<String> TRANSPORT_TYPES = Set.of("BLE");
    /** transport 白名单键集合，未知键直接拒绝。 */
    private static final Set<String> TRANSPORT_KEYS = Set.of("type", "mac", "protocolId");
    private static final Set<String> FORM_FACTORS = Set.of("CAR", "SPIDER", "DOG", "ROBOT");
    private static final Set<String> CAPABILITIES =
            Set.of("MOVE", "PTZ", "MIC", "SPEAKER", "CAMERA", "LIDAR");

    private static final int MAX_NAME_LEN = 128;
    private static final int MAX_CAPABILITIES = 16;

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper mapper;
    private final RobotTelemetryHub hub;
    /** 桥内部 token：未配置即 fail-closed（桥端点一律拒连）。 */
    private final String bridgeToken;

    public RobotRegistryService(JdbcTemplate jdbcTemplate,
            ObjectMapper mapper,
            RobotTelemetryHub hub,
            @Value("${smartops.robot.bridge-token:}") String bridgeToken) {
        this.jdbcTemplate = jdbcTemplate;
        this.mapper = mapper;
        this.hub = hub;
        this.bridgeToken = bridgeToken;
    }

    /** 全量设备列表（含最新登记状态；遥测快照 M1 起由 TelemetryHub 合入）。 */
    public List<Map<String, Object>> listDevices() {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT device_key AS \"deviceKey\", name AS \"name\", form_factor AS \"formFactor\", "
                        + "capabilities AS \"capabilities\", transport AS \"transport\", status AS \"status\", "
                        + "enabled AS \"enabled\", firmware AS \"firmware\", "
                        + "last_seen_at AS \"lastSeenAt\", created_at AS \"createdAt\", updated_at AS \"updatedAt\" "
                        + "FROM robot_device ORDER BY device_key"
        );
        rows.forEach(this::enrich);
        return rows;
    }

    /** 单设备详情；不存在返回 404，与全站口径一致。 */
    public Map<String, Object> deviceStatus(String deviceKey) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT device_key AS \"deviceKey\", name AS \"name\", form_factor AS \"formFactor\", "
                        + "capabilities AS \"capabilities\", transport AS \"transport\", status AS \"status\", "
                        + "enabled AS \"enabled\", firmware AS \"firmware\", "
                        + "last_seen_at AS \"lastSeenAt\", updated_at AS \"updatedAt\" "
                        + "FROM robot_device WHERE device_key = ?",
                deviceKey
        );
        if (rows.isEmpty()) {
            throw new BusinessException(404, "巡检机器人不存在");
        }
        Map<String, Object> device = new LinkedHashMap<>(rows.get(0));
        enrich(device);
        return device;
    }

    /**
     * JSON 列解析 + 合入遥控能力清单。
     *
     * <p>能力清单由后端下发（{@link RobotTeleopProfiles}），前端只渲染不判断类型；
     * 台账里的 form_factor 允许历史脏值，未登记形态返回保守兜底而不是报错。
     */
    private void enrich(Map<String, Object> device) {
        device.put("capabilities", parseJson(device.get("capabilities")));
        device.put("transport", parseJson(device.get("transport")));
        Object formFactor = device.get("formFactor");
        device.put("teleop", RobotTeleopProfiles.forFormFactor(
                formFactor == null ? null : String.valueOf(formFactor)));
    }

    /**
     * 登记/更新设备（幂等按 deviceKey）：存在则更新档案并保留 enabled/status，
     * 不存在则插入且默认禁用。格式校验全部集中在此。
     */
    @Transactional
    public Map<String, Object> upsert(RobotDeviceUpsertRequest request) {
        String deviceKey = requirePattern(request.getDeviceKey(), DEVICE_KEY,
                "deviceKey 仅允许小写字母数字与连字符，2-64 位（ROBOT_INVALID_DEVICE_KEY）");
        String name = request.getName();
        if (name == null || name.isBlank() || name.length() > MAX_NAME_LEN) {
            throw new BusinessException("name 必填且不超过 " + MAX_NAME_LEN + " 字符（ROBOT_INVALID_NAME）");
        }
        String formFactor = requireEnum(request.getFormFactor(), FORM_FACTORS,
                "formFactor 仅允许 CAR/SPIDER/DOG/ROBOT（ROBOT_INVALID_FORM_FACTOR）");
        List<String> capabilities = normalizeCapabilities(request.getCapabilities());
        Map<String, Object> transport = normalizeTransport(request.getTransport());
        String firmware = request.getFirmware();
        if (firmware != null && !firmware.isBlank() && !FIRMWARE.matcher(firmware.strip()).matches()) {
            throw new BusinessException("firmware 仅允许安全字符集，1-64 位（ROBOT_INVALID_FIRMWARE）");
        }

        int updated = jdbcTemplate.update(
                "UPDATE robot_device SET name = ?, form_factor = ?, capabilities = ?, "
                        + "transport = ?, firmware = ? WHERE device_key = ?",
                name.strip(), formFactor, json(capabilities), json(transport),
                firmware == null || firmware.isBlank() ? null : firmware.strip(),
                deviceKey
        );
        if (updated == 0) {
            jdbcTemplate.update(
                    "INSERT INTO robot_device (device_key, name, form_factor, capabilities, "
                            + "transport, status, enabled, firmware) VALUES (?, ?, ?, ?, ?, 'OFFLINE', 0, ?)",
                    deviceKey, name.strip(), formFactor, json(capabilities), json(transport),
                    firmware == null || firmware.isBlank() ? null : firmware.strip()
            );
        }
        return deviceStatus(deviceKey);
    }

    /** 启用/禁用（fail-closed：登记不等于可用，必须显式启用）；不存在返回 404。 */
    @Transactional
    public Map<String, Object> setEnabled(String deviceKey, boolean enabled) {
        deviceStatus(deviceKey);
        jdbcTemplate.update(
                "UPDATE robot_device SET enabled = ? WHERE device_key = ?",
                enabled ? 1 : 0, deviceKey
        );
        return deviceStatus(deviceKey);
    }

    /**
     * 控制类操作的前置门禁：设备必须已登记且已启用。
     * 不存在 404、未启用 409（与全站「状态不允许」口径一致）。
     */
    public Map<String, Object> requireEnabled(String deviceKey) {
        Map<String, Object> device = deviceStatus(deviceKey);
        if (!Boolean.TRUE.equals(device.get("enabled"))
                && !Integer.valueOf(1).equals(device.get("enabled"))) {
            throw new BusinessException(409, "巡检机器人未启用，请先在设备台账启用（ROBOT_DISABLED）");
        }
        return device;
    }

    /** 同步设备运行态到台账（状态由控制服务的内存状态机驱动）。 */
    @Transactional
    public void updateStatus(String deviceKey, String status) {
        jdbcTemplate.update(
                "UPDATE robot_device SET status = ?, last_seen_at = CURRENT_TIMESTAMP WHERE device_key = ?",
                status, deviceKey
        );
    }

    /**
     * 机队自检：真实反映桥连接状态与设备状态分布，不伪装在线。
     * 桥连接以 WebSocket 实际会话为准（M1 起），未连接时不伪造。
     */
    public Map<String, Object> fleetStatus() {
        boolean bridgeTokenConfigured = bridgeToken != null && !bridgeToken.isBlank();
        Map<String, Object> counts = new LinkedHashMap<>();
        for (Map<String, Object> row : jdbcTemplate.queryForList(
                "SELECT status AS \"status\", COUNT(*) AS \"cnt\" FROM robot_device GROUP BY status")) {
            counts.put(String.valueOf(row.get("status")), row.get("cnt"));
        }
        long total = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM robot_device", Long.class);
        long enabled = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM robot_device WHERE enabled = 1", Long.class);

        List<String> connected = hub.connectedDeviceKeys();
        Map<String, Object> bridge = new LinkedHashMap<>();
        bridge.put("tokenConfigured", bridgeTokenConfigured);
        bridge.put("connected", !connected.isEmpty());
        bridge.put("connectedDeviceKeys", connected);
        if (!bridgeTokenConfigured) {
            bridge.put("note", "未配置 SMARTOPS_ROBOT_BRIDGE_TOKEN，桥端点将拒绝所有连接（fail-closed）");
        }

        Map<String, Object> status = new LinkedHashMap<>();
        status.put("phase", "M1");
        status.put("bridge", bridge);
        status.put("deviceTotal", total);
        status.put("deviceEnabled", enabled);
        status.put("statusCounts", counts);
        return status;
    }

    /** 桥内部 token 注释见构造器。 */

    /* ---------------- 校验与序列化 ---------------- */

    private String requirePattern(String value, Pattern pattern, String message) {
        if (value == null || !pattern.matcher(value.strip()).matches()) {
            throw new BusinessException(message);
        }
        return value.strip();
    }

    private String requireEnum(String value, Set<String> allowed, String message) {
        if (value == null || !allowed.contains(value.strip())) {
            throw new BusinessException(message);
        }
        return value.strip();
    }

    private List<String> normalizeCapabilities(List<String> raw) {
        if (raw == null || raw.isEmpty()) {
            throw new BusinessException("capabilities 必填（ROBOT_INVALID_CAPABILITIES）");
        }
        List<String> normalized = new ArrayList<>();
        for (String item : raw) {
            String value = item == null ? "" : item.strip();
            if (!CAPABILITIES.contains(value)) {
                throw new BusinessException("capabilities 含未登记能力：" + value
                        + "，仅允许 MOVE/PTZ/MIC/SPEAKER/CAMERA/LIDAR（ROBOT_INVALID_CAPABILITIES）");
            }
            if (!normalized.contains(value)) {
                normalized.add(value);
            }
        }
        if (normalized.size() > MAX_CAPABILITIES) {
            throw new BusinessException("capabilities 超出上限 " + MAX_CAPABILITIES
                    + "（ROBOT_INVALID_CAPABILITIES）");
        }
        return normalized;
    }

    private Map<String, Object> normalizeTransport(Map<String, Object> raw) {
        if (raw == null || raw.isEmpty()) {
            throw new BusinessException("transport 必填（ROBOT_INVALID_TRANSPORT）");
        }
        for (String key : raw.keySet()) {
            if (!TRANSPORT_KEYS.contains(key)) {
                throw new BusinessException("transport 含未知键：" + key
                        + "（ROBOT_INVALID_TRANSPORT）");
            }
        }
        String type = String.valueOf(raw.getOrDefault("type", "")).strip();
        if (!TRANSPORT_TYPES.contains(type)) {
            throw new BusinessException("transport.type M0 阶段仅支持 BLE（ROBOT_INVALID_TRANSPORT）");
        }
        String mac = String.valueOf(raw.getOrDefault("mac", "")).strip();
        if (!MAC.matcher(mac).matches()) {
            throw new BusinessException("transport.mac 不是合法 MAC 地址（ROBOT_INVALID_TRANSPORT）");
        }
        String protocolId = String.valueOf(raw.getOrDefault("protocolId", "")).strip();
        if (!PROTOCOL_ID.matcher(protocolId).matches()) {
            throw new BusinessException("transport.protocolId 格式非法（ROBOT_INVALID_TRANSPORT）");
        }
        Map<String, Object> transport = new LinkedHashMap<>();
        transport.put("type", type);
        transport.put("mac", mac.toUpperCase());
        transport.put("protocolId", protocolId);
        return transport;
    }

    private String json(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (Exception e) {
            throw new BusinessException("机器人档案序列化失败");
        }
    }

    private Object parseJson(Object raw) {
        if (raw == null) {
            return null;
        }
        try {
            return mapper.readValue(String.valueOf(raw), Object.class);
        } catch (Exception e) {
            return raw;
        }
    }
}
