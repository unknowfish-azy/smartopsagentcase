package com.smartops.integration;

import com.smartops.module.incident.IncidentStatus;
import com.smartops.service.IncidentService;
import com.smartops.vo.IncidentVO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 事件中心闭环的集成测试（真实迁移脚本 + 真实 SQL）。
 *
 * <p>为什么不用纯 Mockito：这条链路的正确性大部分落在 SQL 上
 * （状态机落库、时间线、关联唯一约束、告警 ticket_id 回填），
 * 用替身验证等于没验证。H2 跑的是真实迁移脚本，
 * 所以表结构、约束和幂等性也一并被覆盖。</p>
 *
 * <p>告警本身直接插库：真实告警需要已授权的 SSH 运行连接，
 * 集成测试环境里没有目标机。插库只跳过"怎么产生告警"，不跳过"告警之后的一切"。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:incident_center;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        // 关掉轮询：本测试只验证事件中心自身，避免后台线程干扰断言
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.incident.autobridge.initial-delay-ms=86400000",
        "smartops.incident.sla.initial-delay-ms=86400000"
})
class IncidentCenterIntegrationTest {

    private static final long OWNER = 81L;

    @Autowired IncidentService incidents;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void seed() {
        for (String table : List.of("incident_relation", "incident_event", "incident",
                "sentinel_alert_event", "sentinel_notification", "sentinel_alert",
                "sentinel_alert_rule", "sentinel_metric_sample", "sentinel_script_run",
                "sentinel_script_version", "sentinel_script", "sentinel_task")) {
            if (exists(table)) jdbc.update("DELETE FROM " + table);
        }
        jdbc.update("INSERT INTO sentinel_task(user_id, name, kind, target, interval_sec, enabled) "
                + "VALUES(?,?,?,?,?,1)", OWNER, "prod-web-01", "SSH", "10.0.0.11", 60);
    }

    @Test
    @DisplayName("告警 → 事件：建立事件、写入时间线、双向关联，并回填 ticket_id")
    void createsIncidentFromAlertAndLinksBothSides() {
        long alertId = insertAlert("P1", "OPEN", "prod-web-01：cpu>90");

        IncidentVO incident = incidents.createFromAlert(alertId, OWNER);

        assertThat(incident.getStatus()).isEqualTo(IncidentStatus.OPEN);
        assertThat(incident.getSlaTargetMinutes()).isEqualTo(30);
        assertThat(incident.getSlaDeadline()).isNotNull();

        Map<String, Object> row = jdbc.queryForMap(
                "SELECT status,severity,source,reporter_id,related_asset_type FROM incident WHERE id=?",
                incident.getId());
        assertThat(row.get("status")).isEqualTo("OPEN");
        assertThat(row.get("severity")).isEqualTo("P1");
        assertThat(row.get("source")).isEqualTo("ALERT");
        assertThat(row.get("reporter_id")).isEqualTo(OWNER);

        // 时间线：创建 + 关联告警
        List<Map<String, Object>> events = jdbc.queryForList(
                "SELECT kind,detail FROM incident_event WHERE incident_id=? ORDER BY id", incident.getId());
        assertThat(events).isNotEmpty();
        assertThat(events.get(0).get("kind")).isEqualTo("SYSTEM");

        // 事件侧关联
        Integer relations = jdbc.queryForObject(
                "SELECT COUNT(*) FROM incident_relation WHERE incident_id=? AND relation_type='ALERT' AND ref_id=?",
                Integer.class, incident.getId(), alertId);
        assertThat(relations).isEqualTo(1);

        // 告警侧回填，以及告警时间线留痕
        Long ticketId = jdbc.queryForObject("SELECT ticket_id FROM sentinel_alert WHERE id=?", Long.class, alertId);
        assertThat(ticketId).isEqualTo(incident.getId());
        Integer linked = jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_alert_event WHERE alert_id=? AND kind='INCIDENT_LINKED'",
                Integer.class, alertId);
        assertThat(linked).isEqualTo(1);
    }

    @Test
    @DisplayName("同一告警重复建单保持幂等，不会产生第二个事件")
    void creatingTwiceFromSameAlertIsIdempotent() {
        long alertId = insertAlert("P2", "NOTIFIED", "prod-web-01：memory>90");

        IncidentVO first = incidents.createFromAlert(alertId, OWNER);
        IncidentVO second = incidents.createFromAlert(alertId, OWNER);

        assertThat(second.getId()).isEqualTo(first.getId());
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM incident", Integer.class);
        assertThat(count).isEqualTo(1);
    }

    @Test
    @DisplayName("状态机：ACK → MITIGATING → RESOLVED → CLOSED 全程留痕，非法跳转被拒绝")
    void statusMachinePersistsTimeline() {
        long alertId = insertAlert("P0", "OPEN", "prod-web-01：disk>95");
        IncidentVO created = incidents.createFromAlert(alertId, OWNER);

        incidents.acknowledge(created.getId(), OWNER);
        incidents.startMitigating(created.getId(), OWNER);

        com.smartops.dto.IncidentCloseRequest close = new com.smartops.dto.IncidentCloseRequest();
        close.setRootCause("日志盘写满");
        close.setResolution("清理日志并扩容");
        close.setPostmortem("补充磁盘水位告警");

        // MILESTONE：MITIGATING 不能直接 CLOSED，必须先 RESOLVED
        assertThat(org.junit.jupiter.api.Assertions.assertThrows(
                com.smartops.exception.BusinessException.class,
                () -> incidents.close(created.getId(), OWNER, close))).isNotNull();

        incidents.resolve(created.getId(), OWNER, "已清理");
        IncidentVO closed = incidents.close(created.getId(), OWNER, close);

        assertThat(closed.getStatus()).isEqualTo(IncidentStatus.CLOSED);
        Map<String, Object> row = jdbc.queryForMap(
                "SELECT acknowledged_at, closed_at, root_cause FROM incident WHERE id=?",
                created.getId());
        assertThat(row.get("acknowledged_at")).isNotNull();
        assertThat(row.get("closed_at")).isNotNull();
        assertThat(row.get("root_cause")).isEqualTo("日志盘写满");

        Integer transitions = jdbc.queryForObject(
                "SELECT COUNT(*) FROM incident_event WHERE incident_id=? AND kind='STATUS_CHANGE'",
                Integer.class, created.getId());
        assertThat(transitions).isEqualTo(4); // ACK, MITIGATING, RESOLVED, CLOSED
    }

    @Test
    @DisplayName("SLA 超时只记录一次，重复扫描不重复刷时间线")
    void slaBreachIsRecordedOnce() {
        long alertId = insertAlert("P0", "OPEN", "prod-web-01：cpu>90");
        IncidentVO created = incidents.createFromAlert(alertId, OWNER);
        // 把截止时间拨到过去，模拟已经超时
        jdbc.update("UPDATE incident SET sla_deadline=DATEADD('MINUTE', -5, CURRENT_TIMESTAMP) WHERE id=?",
                created.getId());

        int first = incidents.scanSlaBreaches(50);
        int second = incidents.scanSlaBreaches(50);

        assertThat(first).isEqualTo(1);
        assertThat(second).isZero();
        Integer breaches = jdbc.queryForObject(
                "SELECT COUNT(*) FROM incident_event WHERE incident_id=? AND kind='SLA_BREACH'",
                Integer.class, created.getId());
        assertThat(breaches).isEqualTo(1);
    }

    private long insertAlert(String severity, String status, String title) {
        Long taskId = jdbc.queryForObject("SELECT id FROM sentinel_task WHERE user_id=? ORDER BY id DESC LIMIT 1",
                Long.class, OWNER);
        jdbc.update("INSERT INTO sentinel_alert(task_id, severity, status, title, metric, "
                        + "observed_value, threshold_value, fired_at) VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                taskId, severity, status, title, "cpu", "97.5", "cpu>90");
        return jdbc.queryForObject("SELECT id FROM sentinel_alert ORDER BY id DESC LIMIT 1", Long.class);
    }

    private boolean exists(String table) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM information_schema.tables WHERE LOWER(table_name)=LOWER(?)",
                Integer.class, table);
        return count != null && count > 0;
    }
}
