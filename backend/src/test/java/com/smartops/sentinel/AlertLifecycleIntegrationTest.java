package com.smartops.sentinel;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * P0-03 告警生命周期的集成验证：去重、自动恢复、静默窗口、转派升级、死信与重发、分组聚合。
 *
 * <p>为什么用 Spring 全上下文 + 真实迁移：这一块的正确性几乎全部落在 SQL 上
 * （"最新一条采样"怎么算、静默窗口怎么判、谁能改告警），用 Mapper 替身验证等于没验证。
 * H2 跑的是与生产同一份 Flyway 迁移，因此 {@code V20261105.7__alert_lifecycle.sql}
 * 的加列与建表也一并被覆盖。</p>
 *
 * <p>后台轮询统一推迟到 24 小时后：它们会改告警状态，集成测试里必须由用例自己驱动，
 * 否则断言会被另一个线程改数据而抖动。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:alert_lifecycle;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000",
        "smartops.sentinel.recovery.initial-delay-ms=86400000",
        "smartops.sentinel.dead-letter.initial-delay-ms=86400000"
})
class AlertLifecycleIntegrationTest {

    private static final long OWNER_ID = 81L;
    private static final long PEER_ID = 82L;
    private static final long DISABLED_ID = 83L;
    private static final long STRANGER_ID = 84L;

    private static final SessionUser OWNER = new SessionUser(OWNER_ID, "owner", "operator");
    private static final SessionUser STRANGER = new SessionUser(STRANGER_ID, "stranger", "operator");

    @Autowired JdbcTemplate jdbc;
    @Autowired SentinelService sentinel;
    @Autowired AlertLifecycleService lifecycle;

    @BeforeEach
    void reset() {
        for (String table : List.of("sentinel_notification", "sentinel_alert_event", "sentinel_metric_sample",
                "sentinel_alert", "sentinel_silence", "sentinel_alert_rule", "sentinel_task",
                "sentinel_threshold_template", "team_notification")) {
            jdbc.update("DELETE FROM " + table);
        }
        jdbc.update("DELETE FROM app_user");
        jdbc.update("""
                INSERT INTO app_user(id,username,password_hash,role,enabled)
                VALUES(?,?,?,'operator',TRUE),(?,?,?,'operator',TRUE),(?,?,?,'operator',FALSE),(?,?,?,'operator',TRUE)
                """, OWNER_ID, "owner", "x", PEER_ID, "peer", "x", DISABLED_ID, "disabled", "x", STRANGER_ID, "stranger", "x");
    }

    /* ── 自动恢复 ─────────────────────────────────────────────────────── */

    @Test
    @DisplayName("自动恢复只认最新一条采样，且不越过人工处置中的状态")
    void autoResolveTrustsLatestSampleOnly() {
        LocalDateTime base = LocalDateTime.now();

        // 1) 最新采样仍异常 → 不能判恢复（一次抖动就关单会让真正故障被忽略）
        task(OWNER_ID, 4101L);
        alert(4201L, 4101L, "P1", "OPEN", base.minusMinutes(10));
        sample(4101L, base.minusMinutes(9), true);
        sample(4101L, base.minusMinutes(8), false);
        sample(4101L, base.minusMinutes(7), true);

        // 2) 最新采样正常 → 应自动进入待关闭
        task(OWNER_ID, 4102L);
        alert(4202L, 4102L, "P2", "NOTIFIED", base.minusMinutes(10));
        sample(4102L, base.minusMinutes(9), true);
        sample(4102L, base.minusMinutes(8), false);

        // 3) 从未采样 → 不能凭"没有数据"判恢复
        task(OWNER_ID, 4103L);
        alert(4203L, 4103L, "P2", "OPEN", base.minusMinutes(10));

        // 4) 已在人工处置中 → 自动恢复不介入
        task(OWNER_ID, 4104L);
        alert(4204L, 4104L, "P1", "PENDING_APPROVAL", base.minusMinutes(10));
        sample(4104L, base.minusMinutes(8), false);

        // 5) 正常采样发生在告警之前 → 不能用旧数据关新告警
        task(OWNER_ID, 4105L);
        alert(4205L, 4105L, "P3", "OPEN", base.minusMinutes(2));
        sample(4105L, base.minusMinutes(5), false);

        int resolved = lifecycle.resolveRecoveredAlerts(50);

        assertThat(resolved).isEqualTo(1);
        assertThat(status(4201L)).isEqualTo("OPEN");
        assertThat(status(4202L)).isEqualTo("RESOLVED");
        assertThat(status(4203L)).isEqualTo("OPEN");
        assertThat(status(4204L)).isEqualTo("PENDING_APPROVAL");
        assertThat(status(4205L)).isEqualTo("OPEN");

        assertThat(jdbc.queryForObject("SELECT recovered_at FROM sentinel_alert WHERE id=?", Timestamp.class, 4202L))
                .isNotNull();
        assertThat(jdbc.queryForObject("SELECT resolved_at FROM sentinel_alert WHERE id=?", Timestamp.class, 4202L))
                .isNotNull();
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_alert_event WHERE alert_id=? AND kind='RECOVERED'", Integer.class, 4202L))
                .isEqualTo(1);
    }

    /* ── 去重与静默 ───────────────────────────────────────────────────── */

    @Test
    @DisplayName("同一事件只开一条未结告警，且静默窗口内不新建告警")
    void dedupeAndSilenceGateAlertCreation() {
        long taskId = 4111L;
        taskWithTemplate(OWNER_ID, taskId, 6101L, "mem-90", "[{\"metric\":\"memory\",\"operator\":\"gt\",\"value\":90}]");
        Instant now = Instant.now();
        SentinelService.TaskView view = taskView(taskId, 6101L);

        // 首次越界且防抖已完成 → 建一条告警
        setBreach(taskId, now.minusSeconds(300));
        sentinel.evaluate(view, Map.of("memory", 95.0), now);
        assertThat(alertCount(taskId)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT group_key FROM sentinel_alert WHERE task_id=?", String.class, taskId))
                .isEqualTo("task:" + taskId);

        // 同一任务再次越界：已有未结告警 → 不重复开单
        setBreach(taskId, now.minusSeconds(300));
        sentinel.evaluate(view, Map.of("memory", 96.0), now.plusSeconds(1));
        assertThat(alertCount(taskId)).isEqualTo(1);

        // 告警被人工关闭后，进入静默窗口 → 越界也不新建
        jdbc.update("UPDATE sentinel_alert SET status='CLOSED' WHERE task_id=?", taskId);
        long silenceId = createSilence("GLOBAL", null, "版本发布窗口", now);
        setBreach(taskId, now.minusSeconds(300));
        sentinel.evaluate(view, Map.of("memory", 97.0), now.plusSeconds(2));
        assertThat(alertCount(taskId)).isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_alert WHERE task_id=? AND status='OPEN'", Integer.class, taskId))
                .isZero();

        // 取消静默后同样的越界会正常建单 —— 证明前面拦住它的是静默，而不是别的原因
        lifecycle.cancelSilence(OWNER, silenceId);
        setBreach(taskId, now.minusSeconds(300));
        sentinel.evaluate(view, Map.of("memory", 97.0), now.plusSeconds(3));
        assertThat(alertCount(taskId)).isEqualTo(2);
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_alert WHERE task_id=? AND status='OPEN'", Integer.class, taskId))
                .isEqualTo(1);
    }

    @Test
    @DisplayName("静默窗口内通知被跳过并留痕；取消静默后通知恢复")
    void silenceSuppressesNotificationPath() {
        long alertId = alert(4211L, task(OWNER_ID, 4112L), "P2", "OPEN", LocalDateTime.now());
        long silenceId = createSilence("GLOBAL", null, "变更窗口", Instant.now());

        Map<String, String> silenced = sentinel.notifyStakeholders(alertId, OWNER_ID);
        assertThat(silenced).containsEntry("silenced", "true");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_notification WHERE alert_id=?",
                Integer.class, alertId)).isZero();
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_alert_event WHERE alert_id=? AND kind='SILENCED'", Integer.class, alertId))
                .isEqualTo(1);

        lifecycle.cancelSilence(OWNER, silenceId);
        Map<String, String> delivered = sentinel.notifyStakeholders(alertId, OWNER_ID);
        assertThat(delivered).containsEntry("inapp", "sent");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM team_notification WHERE user_id=?",
                Integer.class, OWNER_ID)).isEqualTo(1);
    }

    @Test
    @DisplayName("静默窗口的边界校验：范围、时长、原因、任务归属")
    void silenceValidation() {
        LocalDateTime start = LocalDateTime.now();

        assertThatThrownBy(() -> lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest("TEAM", null, "原因", start, start.plusHours(1))))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("GLOBAL / TASK");

        assertThatThrownBy(() -> lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest("GLOBAL", null, "", start, start.plusHours(1))))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("原因");

        assertThatThrownBy(() -> lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest("GLOBAL", null, "长假", start, start.plusDays(8))))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("7 天");

        task(STRANGER_ID, 4113L);
        assertThatThrownBy(() -> lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest("TASK", 4113L, "别人的任务", start, start.plusHours(1))))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("无权限");

        task(OWNER_ID, 4114L);
        long silenceId = createSilence("TASK", 4114L, "自己的任务", Instant.now());
        assertThat(AlertSilence.isActive(jdbc, 4114L, Instant.now())).isTrue();
        assertThat(AlertSilence.isActive(jdbc, 4113L, Instant.now())).isFalse();

        assertThatThrownBy(() -> lifecycle.cancelSilence(STRANGER, silenceId))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("无权限");
        lifecycle.cancelSilence(OWNER, silenceId);
        assertThat(AlertSilence.isActive(jdbc, 4114L, Instant.now())).isFalse();
    }

    /* ── 转派 / 升级 ─────────────────────────────────────────────────── */

    @Test
    @DisplayName("转派只接受启用的账号，升级只能往上调")
    void transferAndEscalate() {
        long alertId = alert(4221L, task(OWNER_ID, 4121L), "P2", "OPEN", LocalDateTime.now());

        lifecycle.transfer(OWNER, alertId, PEER_ID, "换班处理");
        assertThat(jdbc.queryForObject("SELECT assignee_id FROM sentinel_alert WHERE id=?", Long.class, alertId))
                .isEqualTo(PEER_ID);
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_alert_event WHERE alert_id=? AND kind='TRANSFERRED'", Integer.class, alertId))
                .isEqualTo(1);

        assertThatThrownBy(() -> lifecycle.transfer(OWNER, alertId, DISABLED_ID, null))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("停用");
        assertThatThrownBy(() -> lifecycle.transfer(STRANGER, alertId, PEER_ID, null))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("无权限");

        assertThat(lifecycle.escalate(OWNER, alertId, "P1", "影响面扩大")).isEqualTo("P1");
        assertThat(jdbc.queryForObject("SELECT severity FROM sentinel_alert WHERE id=?", String.class, alertId))
                .isEqualTo("P1");
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_alert_event WHERE alert_id=? AND kind='ESCALATED'", Integer.class, alertId))
                .isEqualTo(1);

        // 下行与非法级别都必须拒绝：升级不是改级别的后门
        assertThatThrownBy(() -> lifecycle.escalate(OWNER, alertId, "P2", null))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("只能提高");
        assertThatThrownBy(() -> lifecycle.escalate(OWNER, alertId, "P9", null))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("P0-P3");
    }

    /* ── 死信 / 重发 ─────────────────────────────────────────────────── */

    @Test
    @DisplayName("重试耗尽的投递标为死信并保留记录；重发按原渠道与目标执行")
    void deadLetterAndRetry() {
        long alertId = alert(4231L, task(OWNER_ID, 4131L), "P2", "OPEN", LocalDateTime.now());
        jdbc.update("""
                INSERT INTO sentinel_notification(alert_id,channel,target,status,attempts,error_detail)
                VALUES(?,?,?,?,?,?), (?,?,?,?,?,?)
                """, alertId, "webhook", "https://no-such-host.invalid/hook", "failed", 5, "HTTP 502",
                alertId, "email", "ops@example.test", "failed", 1, "timeout");

        int marked = lifecycle.sweepDeadLetters(3);
        assertThat(marked).isEqualTo(1);
        assertThat(deadLettered(alertId, "webhook")).isTrue();
        assertThat(deadLettered(alertId, "email")).isFalse();

        Map<String, String> results = lifecycle.retryNotification(OWNER, alertId);
        // webhook 指向无法解析的主机 → 拒绝；邮件未配置 SMTP → 如实 not_configured
        assertThat(results).containsKeys("webhook", "email");
        assertThat(results.get("email")).isEqualTo("not_configured");

        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_notification WHERE alert_id=? AND dead_lettered=FALSE",
                Integer.class, alertId)).isEqualTo(2);
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM sentinel_notification WHERE alert_id=? AND status='failed'",
                Integer.class, alertId)).isZero();

        assertThatThrownBy(() -> lifecycle.retryNotification(STRANGER, alertId))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("无权限");
    }

    @Test
    @DisplayName("分组聚合：同一 group_key 的多条告警合成一组，按未关数量排序")
    void groupsAggregateByKey() {
        task(OWNER_ID, 4141L);
        task(OWNER_ID, 4142L);
        alert(4241L, 4141L, "P1", "OPEN", LocalDateTime.now().minusMinutes(5), "svc:order");
        alert(4242L, 4142L, "P2", "NOTIFIED", LocalDateTime.now().minusMinutes(4), "svc:order");
        alert(4243L, 4142L, "P0", "OPEN", LocalDateTime.now().minusMinutes(3));

        List<AlertLifecycleService.GroupView> groups = lifecycle.groups(OWNER, 10);

        assertThat(groups).hasSize(2);
        AlertLifecycleService.GroupView order = groups.stream()
                .filter(group -> "svc:order".equals(group.groupKey())).findFirst().orElseThrow();
        assertThat(order.total()).isEqualTo(2);
        assertThat(order.active()).isEqualTo(2);
        assertThat(order.maxSeverity()).isEqualTo("P1");
        // 没有 group_key 的告警仍按任务归组，不会被漏掉
        AlertLifecycleService.GroupView fallback = groups.stream()
                .filter(group -> ("task:" + 4142L).equals(group.groupKey())).findFirst().orElseThrow();
        assertThat(fallback.total()).isEqualTo(1);
        assertThat(fallback.maxSeverity()).isEqualTo("P0");

        assertThat(lifecycle.groups(STRANGER, 10)).isEmpty();
    }

    /* ── 夹具 ─────────────────────────────────────────────────────────── */

    private long task(long userId, long id) {
        jdbc.update("""
                INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled)
                VALUES(?,?,?,'system','memory',60,1)
                """, id, userId, "web-" + id);
        return id;
    }

    private void taskWithTemplate(long userId, long id, long templateId, String name, String rulesJson) {
        // H2 的 JSON 列会把普通字符串当成"JSON 字符串值"（外面多一层引号），
        // 必须用 FORMAT JSON 才会按文档存；MySQL 的 JSON 列两者都按文档解析。
        jdbc.update("""
                INSERT INTO sentinel_threshold_template(id,user_id,name,rules_json,severity,debounce_sec)
                VALUES(?,?,?,? FORMAT JSON, 'P1', 0)
                """, templateId, userId, name, rulesJson);
        jdbc.update("""
                INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,template_id,enabled)
                VALUES(?,?,?,'system','memory',60,?,1)
                """, id, userId, "web-" + id, templateId);
    }

    private SentinelService.TaskView taskView(long taskId, Long templateId) {
        return new SentinelService.TaskView(taskId, "web-" + taskId, "system", "memory", null, 60,
                templateId, true, null, null, null, 0, 0, null, null);
    }

    private void setBreach(long taskId, Instant since) {
        jdbc.update("UPDATE sentinel_task SET breached_since=? WHERE id=?",
                Timestamp.from(since), taskId);
    }

    private long alert(long id, long taskId, String severity, String status, LocalDateTime firedAt) {
        return alert(id, taskId, severity, status, firedAt, null);
    }

    private long alert(long id, long taskId, String severity, String status, LocalDateTime firedAt, String groupKey) {
        jdbc.update("""
                INSERT INTO sentinel_alert(id,task_id,severity,status,title,metric,observed_value,threshold_value,fired_at,group_key)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """, id, taskId, severity, status, "web-" + taskId + "：内存越界", "memory", "95.0", "memory > 90",
                Timestamp.valueOf(firedAt), groupKey);
        return id;
    }

    private void sample(long taskId, LocalDateTime at, boolean abnormal) {
        jdbc.update("INSERT INTO sentinel_metric_sample(task_id,sampled_at,metric,value_num,abnormal) VALUES(?,?,?,?,?)",
                taskId, Timestamp.valueOf(at), "memory", abnormal ? 95.0 : 40.0, abnormal ? 1 : 0);
    }

    private String status(long alertId) {
        return jdbc.queryForObject("SELECT status FROM sentinel_alert WHERE id=?", String.class, alertId);
    }

    private int alertCount(long taskId) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_alert WHERE task_id=?", Integer.class, taskId);
    }

    private boolean deadLettered(long alertId, String channel) {
        return Boolean.TRUE.equals(jdbc.queryForObject(
                "SELECT dead_lettered FROM sentinel_notification WHERE alert_id=? AND channel=?",
                Boolean.class, alertId, channel));
    }

    private long createSilence(String scope, Long scopeId, String reason, Instant moment) {
        LocalDateTime start = LocalDateTime.ofInstant(moment, java.time.ZoneId.systemDefault()).minusHours(1);
        LocalDateTime end = LocalDateTime.ofInstant(moment, java.time.ZoneId.systemDefault()).plusHours(1);
        return lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest(scope, scopeId, reason, start, end)).id();
    }
}
