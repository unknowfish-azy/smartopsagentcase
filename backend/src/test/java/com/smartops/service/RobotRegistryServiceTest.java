package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.robot.RobotDeviceUpsertRequest;
import com.smartops.exception.BusinessException;
import com.smartops.robot.RobotTeleopProfiles;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** 巡检机器人设备台账 M0：fail-closed 默认禁用、白名单校验、幂等更新保留启用态。 */
class RobotRegistryServiceTest {

    private JdbcTemplate jdbc;
    private RobotRegistryService service;
    private RobotRegistryService serviceWithToken;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource(
                "jdbc:h2:mem:robot-registry-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE robot_device ("
                + "id BIGINT PRIMARY KEY AUTO_INCREMENT, "
                + "device_key VARCHAR(64) NOT NULL UNIQUE, "
                + "name VARCHAR(128) NOT NULL, "
                + "form_factor VARCHAR(16) NOT NULL, "
                + "capabilities VARCHAR(512) NOT NULL, "
                + "transport VARCHAR(512) NOT NULL, "
                + "status VARCHAR(16) NOT NULL DEFAULT 'OFFLINE', "
                + "enabled TINYINT(1) NOT NULL DEFAULT 0, "
                + "firmware VARCHAR(64), "
                + "last_seen_at DATETIME, "
                + "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                + "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        service = new RobotRegistryService(jdbc, new ObjectMapper(),
                new com.smartops.robot.RobotTelemetryHub(new ObjectMapper()), "");
        serviceWithToken = new RobotRegistryService(jdbc, new ObjectMapper(),
                new com.smartops.robot.RobotTelemetryHub(new ObjectMapper()), "test-token");
    }

    private RobotDeviceUpsertRequest validRequest() {
        RobotDeviceUpsertRequest request = new RobotDeviceUpsertRequest();
        request.setDeviceKey("robot-car-01");
        request.setName("一号巡检车");
        request.setFormFactor("CAR");
        request.setCapabilities(List.of("MOVE", "CAMERA", "SPEAKER"));
        request.setTransport(Map.of("type", "BLE", "mac", "aa:bb:cc:dd:ee:ff", "protocolId", "generic-ble-car-v1"));
        return request;
    }

    @Test
    void upsertInsertsDisabledDeviceByDefault() {
        Map<String, Object> device = service.upsert(validRequest());
        // H2/MySQL 对 TINYINT(1) 可能返回 Boolean 或 Integer，两者都视为默认禁用
        assertThat(device.get("enabled")).isIn(List.of(false, 0, 0L));
        assertThat(device.get("status")).isEqualTo("OFFLINE");
        // MAC 统一大写归一
        assertThat(String.valueOf(device.get("transport"))).contains("AA:BB:CC:DD:EE:FF");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM robot_device", Integer.class)).isEqualTo(1);
    }

    @Test
    void upsertUpdateKeepsEnabledAndStatus() {
        service.upsert(validRequest());
        service.setEnabled("robot-car-01", true);
        Map<String, Object> updated = service.upsert(validRequest());
        assertThat(updated.get("enabled")).isIn(List.of(true, 1, 1L));
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM robot_device", Integer.class)).isEqualTo(1);
    }

    @Test
    void upsertRejectsInvalidProfiles() {
        RobotDeviceUpsertRequest badKey = validRequest();
        badKey.setDeviceKey("Robot Car");
        assertThatThrownBy(() -> service.upsert(badKey))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_INVALID_DEVICE_KEY");

        RobotDeviceUpsertRequest badFactor = validRequest();
        badFactor.setFormFactor("DRONE");
        assertThatThrownBy(() -> service.upsert(badFactor))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_INVALID_FORM_FACTOR");

        RobotDeviceUpsertRequest badCap = validRequest();
        badCap.setCapabilities(List.of("FLY"));
        assertThatThrownBy(() -> service.upsert(badCap))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_INVALID_CAPABILITIES");

        RobotDeviceUpsertRequest badMac = validRequest();
        badMac.setTransport(Map.of("type", "BLE", "mac", "not-a-mac", "protocolId", "generic-ble-car-v1"));
        assertThatThrownBy(() -> service.upsert(badMac))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_INVALID_TRANSPORT");

        RobotDeviceUpsertRequest unknownKey = validRequest();
        unknownKey.setTransport(Map.of("type", "BLE", "mac", "AA:BB:CC:DD:EE:FF",
                "protocolId", "generic-ble-car-v1", "pin", "1234"));
        assertThatThrownBy(() -> service.upsert(unknownKey))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_INVALID_TRANSPORT");
    }

    @Test
    void setEnabledReturns404ForMissingDevice() {
        assertThatThrownBy(() -> service.setEnabled("robot-dog-01", true))
                .isInstanceOf(BusinessException.class)
                .extracting("code").isEqualTo(404);
    }

    @Test
    void deviceStatusParsesJsonColumns() {
        service.upsert(validRequest());
        Map<String, Object> status = service.deviceStatus("robot-car-01");
        assertThat(status.get("capabilities")).isEqualTo(List.of("MOVE", "CAMERA", "SPEAKER"));
        assertThat(status.get("formFactor")).isEqualTo("CAR");
    }

    @Test
    @SuppressWarnings("unchecked")
    void devicesCarryTeleopCapabilityFromSingleSource() {
        service.upsert(validRequest());
        Map<String, Object> car = service.listDevices().get(0);
        // 列表接口也必须解析 JSON 列，否则前端拿到字符串无法判 MOVE 能力
        assertThat(car.get("capabilities")).isEqualTo(List.of("MOVE", "CAMERA", "SPEAKER"));
        Map<String, Object> carTeleop = (Map<String, Object>) car.get("teleop");
        assertThat(carTeleop.get("axes")).isEqualTo(List.of("forward", "yaw"));
        assertThat(carTeleop.get("known")).isEqualTo(true);

        // 四足：可横移 + 步态，且限速低于轮式
        Map<String, Object> dogTeleop = RobotTeleopProfiles.forFormFactor("dog");
        assertThat(dogTeleop.get("axes")).isEqualTo(List.of("forward", "lateral", "yaw", "gait"));
        assertThat(dogTeleop.get("gaits")).isEqualTo(List.of("TROT", "WALK", "STAND"));
        assertThat(((Map<String, Object>) dogTeleop.get("maxSpeed")).get("linear"))
                .isEqualTo(0.35);

        // 未登记形态不抛异常，给保守兜底并标记 known=false
        Map<String, Object> unknown = RobotTeleopProfiles.forFormFactor("HOVER");
        assertThat(unknown.get("known")).isEqualTo(false);
        assertThat(unknown.get("axes")).isEqualTo(List.of("forward", "yaw"));
    }

    @Test
    void fleetStatusReportsBridgeHonestState() {
        service.upsert(validRequest());
        Map<String, Object> status = service.fleetStatus();
        assertThat(status.get("phase")).isEqualTo("M1");
        assertThat(status.get("deviceTotal")).isEqualTo(1L);
        assertThat(status.get("deviceEnabled")).isEqualTo(0L);
        @SuppressWarnings("unchecked")
        Map<String, Object> bridge = (Map<String, Object>) status.get("bridge");
        assertThat(bridge.get("tokenConfigured")).isEqualTo(false);
        assertThat(bridge.get("connected")).isEqualTo(false);

        Map<String, Object> statusWithToken = serviceWithToken.fleetStatus();
        @SuppressWarnings("unchecked")
        Map<String, Object> bridgeWithToken = (Map<String, Object>) statusWithToken.get("bridge");
        assertThat(bridgeWithToken.get("tokenConfigured")).isEqualTo(true);
    }
}
