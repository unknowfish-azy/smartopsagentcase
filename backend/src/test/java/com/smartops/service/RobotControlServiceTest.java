package com.smartops.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.dto.robot.RobotDeviceUpsertRequest;
import com.smartops.exception.BusinessException;
import com.smartops.robot.RobotMode;
import com.smartops.robot.RobotTelemetryHub;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/** 巡检机器人双态控制：状态机、命令门禁、限流、急停旁路、审计。 */
class RobotControlServiceTest {

    private static final String DEVICE = "robot-car-01";

    private JdbcTemplate jdbc;
    private RobotTelemetryHub hub;
    private RobotFrameService frames;
    private RobotControlService control;

    @BeforeEach
    void setUp() {
        DriverManagerDataSource ds = new DriverManagerDataSource(
                "jdbc:h2:mem:robot-control-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE robot_device ("
                + "id BIGINT PRIMARY KEY AUTO_INCREMENT, device_key VARCHAR(64) NOT NULL UNIQUE, "
                + "name VARCHAR(128) NOT NULL, form_factor VARCHAR(16) NOT NULL, "
                + "capabilities VARCHAR(512) NOT NULL, transport VARCHAR(512) NOT NULL, "
                + "status VARCHAR(16) NOT NULL DEFAULT 'OFFLINE', enabled TINYINT(1) NOT NULL DEFAULT 0, "
                + "firmware VARCHAR(64), last_seen_at DATETIME, "
                + "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                + "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbc.execute("CREATE TABLE robot_command_log ("
                + "id BIGINT PRIMARY KEY AUTO_INCREMENT, device_key VARCHAR(64) NOT NULL, "
                + "mode VARCHAR(16) NOT NULL, op VARCHAR(16) NOT NULL, params VARCHAR(1024), "
                + "accepted TINYINT(1) NOT NULL, reject_code VARCHAR(32), operator VARCHAR(64), "
                + "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbc.execute("CREATE TABLE robot_task ("
                + "id BIGINT PRIMARY KEY AUTO_INCREMENT, device_key VARCHAR(64) NOT NULL, "
                + "plan_id VARCHAR(64), route VARCHAR(2048) NOT NULL, "
                + "status VARCHAR(16) NOT NULL DEFAULT 'PENDING', progress INT NOT NULL DEFAULT 0, "
                + "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                + "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)");

        ObjectMapper mapper = new ObjectMapper();
        hub = mock(RobotTelemetryHub.class);
        frames = mock(RobotFrameService.class);
        when(hub.connectedDeviceKeys()).thenReturn(List.of());
        when(hub.bridgeConnected(anyString())).thenReturn(true);
        when(hub.sendToBridge(anyString(), anyString(), any())).thenReturn(true);

        RobotRegistryService registry = new RobotRegistryService(jdbc, mapper, hub, "");
        RobotDeviceUpsertRequest request = new RobotDeviceUpsertRequest();
        request.setDeviceKey(DEVICE);
        request.setName("一号巡检车");
        request.setFormFactor("CAR");
        request.setCapabilities(List.of("MOVE", "CAMERA"));
        request.setTransport(Map.of("type", "BLE", "mac", "AA:BB:CC:DD:EE:FF",
                "protocolId", "generic-ble-car-v1"));
        registry.upsert(request);
        registry.setEnabled(DEVICE, true);

        control = new RobotControlService(registry, hub, frames, jdbc, 600);
    }

    private Map<String, Object> moveParams() {
        return Map.of("x", 0.5, "y", 0, "theta", 0, "speed", 0.4, "ttlMs", 200);
    }

    @Test
    void bridgeOnlineMovesOfflineDeviceToIdle() {
        assertThat(control.modeOf(DEVICE)).isEqualTo(RobotMode.OFFLINE);
        control.onBridgeOnline(DEVICE);
        assertThat(control.modeOf(DEVICE)).isEqualTo(RobotMode.IDLE);
        assertThat(jdbc.queryForObject(
                "SELECT status FROM robot_device WHERE device_key = ?", String.class, DEVICE))
                .isEqualTo("IDLE");
    }

    @Test
    void moveRejectedWhenNotInHumanControl() {
        control.onBridgeOnline(DEVICE);
        assertThatThrownBy(() -> control.command(DEVICE, "CONSOLE", "MOVE", moveParams(), "alice"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_NOT_HUMAN_CONTROL");
        // 被拒命令同样留审计
        assertThat(jdbc.queryForObject(
                "SELECT reject_code FROM robot_command_log ORDER BY id DESC LIMIT 1", String.class))
                .isEqualTo("ROBOT_NOT_HUMAN_CONTROL");
    }

    @Test
    void moveAcceptedAfterSwitchingToHumanControl() {
        control.onBridgeOnline(DEVICE);
        control.switchMode(DEVICE, RobotMode.HUMAN_CONTROL, "alice");
        Map<String, Object> result = control.command(DEVICE, "CONSOLE", "MOVE", moveParams(), "alice");
        assertThat(result.get("accepted")).isEqualTo(true);
        assertThat(result.get("mode")).isEqualTo("HUMAN_CONTROL");
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM robot_command_log WHERE accepted = 1", Integer.class)).isEqualTo(1);
    }

    @Test
    void illegalTransitionIsRejected() {
        control.onBridgeOnline(DEVICE);
        control.switchMode(DEVICE, RobotMode.HUMAN_CONTROL, "alice");
        control.emergencyStop(DEVICE, "alice");
        // 急停态不能直接进入自主态，必须人工复位
        assertThatThrownBy(() -> control.switchMode(DEVICE, RobotMode.AUTONOMOUS, "alice"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_INVALID_TRANSITION");
    }

    @Test
    void paramOutOfRangeRejectedWithRuleCode() {
        control.onBridgeOnline(DEVICE);
        control.switchMode(DEVICE, RobotMode.HUMAN_CONTROL, "alice");
        Map<String, Object> bad = Map.of("x", 2.5, "y", 0, "theta", 0, "speed", 0.4, "ttlMs", 200);
        assertThatThrownBy(() -> control.command(DEVICE, "CONSOLE", "MOVE", bad, "alice"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("摇杆量必须在 -1~1 之间");
        assertThat(jdbc.queryForObject(
                "SELECT reject_code FROM robot_command_log ORDER BY id DESC LIMIT 1", String.class))
                .isEqualTo("ROBOT_PARAM_OUT_OF_RANGE");
    }

    @Test
    void unknownOpRejected() {
        control.onBridgeOnline(DEVICE);
        assertThatThrownBy(() -> control.command(DEVICE, "CONSOLE", "FLY", Map.of(), "alice"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("不支持的机器人操作");
    }

    @Test
    void quadrupedGaitAcceptedAndUnknownGaitRejected() {
        control.onBridgeOnline(DEVICE);
        control.switchMode(DEVICE, RobotMode.HUMAN_CONTROL, "alice");
        Map<String, Object> trot = new java.util.HashMap<>(moveParams());
        trot.put("gait", "trot");
        assertThat(control.command(DEVICE, "CONSOLE", "MOVE", trot, "alice").get("accepted"))
                .isEqualTo(true);

        Map<String, Object> fly = new java.util.HashMap<>(moveParams());
        fly.put("gait", "FLY");
        assertThatThrownBy(() -> control.command(DEVICE, "CONSOLE", "MOVE", fly, "alice"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("步态仅允许 TROT/WALK/STAND");
    }

    @Test
    void bridgeOfflineReturns503() {
        control.onBridgeOnline(DEVICE);
        control.switchMode(DEVICE, RobotMode.HUMAN_CONTROL, "alice");
        when(hub.sendToBridge(anyString(), anyString(), any())).thenReturn(false);
        assertThatThrownBy(() -> control.command(DEVICE, "CONSOLE", "MOVE", moveParams(), "alice"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_BRIDGE_OFFLINE");
    }

    @Test
    void emergencyStopWorksFromAnyState() {
        control.onBridgeOnline(DEVICE);
        Map<String, Object> result = control.emergencyStop(DEVICE, "alice");
        assertThat(result.get("mode")).isEqualTo("E_STOP");
        assertThat(result.get("deliveredToBridge")).isEqualTo(true);
        // 复位回到 IDLE（桥在线）
        assertThat(control.reset(DEVICE, "alice").get("mode")).isEqualTo("IDLE");
    }

    @Test
    void rateLimitBlocksBurstCommands() {
        control.onBridgeOnline(DEVICE);
        control.switchMode(DEVICE, RobotMode.HUMAN_CONTROL, "alice");
        for (int i = 0; i < 20; i++) {
            control.command(DEVICE, "CONSOLE", "MOVE", moveParams(), "alice");
        }
        assertThatThrownBy(() -> control.command(DEVICE, "CONSOLE", "MOVE", moveParams(), "alice"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_RATE_LIMITED");
    }

    @Test
    void brainSourceCannotDriveInHumanMode() {
        control.onBridgeOnline(DEVICE);
        control.switchMode(DEVICE, RobotMode.HUMAN_CONTROL, "alice");
        assertThatThrownBy(() -> control.command(DEVICE, "BRAIN", "MOVE", moveParams(), "brain"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("ROBOT_NOT_AUTONOMOUS");
    }

    @Test
    void switchingAwayFromAutonomousPausesRunningTask() {
        control.onBridgeOnline(DEVICE);
        jdbc.update("INSERT INTO robot_task (device_key, route, status) VALUES (?, ?, 'RUNNING')",
                DEVICE, "[{\"x\":0,\"y\":0}]");
        control.switchMode(DEVICE, RobotMode.AUTONOMOUS, "alice");
        control.switchMode(DEVICE, RobotMode.HUMAN_CONTROL, "alice");
        assertThat(jdbc.queryForObject(
                "SELECT status FROM robot_task WHERE device_key = ?", String.class, DEVICE))
                .isEqualTo("PAUSED");
    }
}
