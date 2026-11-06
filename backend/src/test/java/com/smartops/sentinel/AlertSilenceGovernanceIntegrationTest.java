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

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-09 静默治理：审批、TTL、外部同步状态与撤销都必须是可验证的真实语义。
 *
 * <p>用真实迁移 + 真实 SQL：静默是否生效完全取决于 SQL 条件，
 * 用替身验证等于没验证。后台轮询统一推迟，避免和断言抢数据。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:alert_silence_governance;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000",
        "smartops.sentinel.recovery.initial-delay-ms=86400000",
        "smartops.sentinel.dead-letter.initial-delay-ms=86400000",
        "smartops.alerts.alertmanager.url="
})
class AlertSilenceGovernanceIntegrationTest {

    private static final long OWNER_ID = 91L;
    private static final long ADMIN_ID = 92L;
    private static final long TASK_ID = 5101L;

    private static final SessionUser OWNER = new SessionUser(OWNER_ID, "owner", "operator");
    private static final SessionUser ADMIN = new SessionUser(ADMIN_ID, "admin", "admin");

    @Autowired JdbcTemplate jdbc;
    @Autowired AlertLifecycleService lifecycle;

    @BeforeEach
    void reset() {
        for (String table : List.of("sentinel_notification", "sentinel_alert_event", "sentinel_metric_sample",
                "sentinel_alert", "sentinel_silence", "sentinel_alert_rule", "sentinel_task")) {
            jdbc.update("DELETE FROM " + table);
        }
        jdbc.update("DELETE FROM app_user");
        jdbc.update("""
                INSERT INTO app_user(id,username,password_hash,role,enabled)
                VALUES(?,?,?,?,TRUE),(?,?,?,?,TRUE)
                """, OWNER_ID, "owner", "x", "operator", ADMIN_ID, "admin", "x", "admin");
        jdbc.update("INSERT INTO sentinel_task(id,user_id,name,kind,target,interval_sec,enabled) "
                + "VALUES(?,?,?,'system','memory',60,1)", TASK_ID, OWNER_ID, "web-" + TASK_ID);
    }

    @Test
    @DisplayName("超过 24 小时的全局静默非管理员申请后待审批，且审批前不抑制告警")
    void longGlobalSilenceRequiresApprovalBeforeTakingEffect() {
        LocalDateTime start = LocalDateTime.now().minusHours(1);
        LocalDateTime end = start.plusHours(30);

        AlertLifecycleService.SilenceView view = lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest("GLOBAL", null, "大版本发布窗口", start, end));

        assertThat(view.status()).isEqualTo("PENDING_APPROVAL");
        assertThat(view.approvedBy()).isNull();
        assertThat(view.active()).isFalse();
        assertThat(AlertSilence.isActive(jdbc, TASK_ID, Instant.now())).isFalse();
        // 没配置外部平台时必须如实标记，而不是"同步成功"
        assertThat(view.externalStatus()).isEqualTo("NOT_CONFIGURED");

        assertThatThrownBy(() -> lifecycle.approveSilence(OWNER, view.id()))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("管理员");

        AlertLifecycleService.SilenceView approved = lifecycle.approveSilence(ADMIN, view.id());
        assertThat(approved.status()).isEqualTo("ACTIVE");
        assertThat(approved.approvedBy()).isEqualTo(ADMIN_ID);
        assertThat(approved.active()).isTrue();
        assertThat(AlertSilence.isActive(jdbc, TASK_ID, Instant.now())).isTrue();
    }

    @Test
    @DisplayName("已生效的静默不能被重复审批，避免事后改写审批人")
    void activeSilenceCannotBeApprovedAgain() {
        long silenceId = lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest("TASK", TASK_ID, "短窗口维护",
                        LocalDateTime.now().minusMinutes(1), LocalDateTime.now().plusHours(2))).id();

        assertThatThrownBy(() -> lifecycle.approveSilence(ADMIN, silenceId))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("不在待审批状态");
    }

    @Test
    @DisplayName("任务级静默无需审批即可生效，且记录审批人本人")
    void taskShortSilenceTakesEffectImmediately() {
        AlertLifecycleService.SilenceView view = lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest("TASK", TASK_ID, "例行维护",
                        LocalDateTime.now().minusMinutes(1), LocalDateTime.now().plusHours(2)));

        assertThat(view.status()).isEqualTo("ACTIVE");
        assertThat(view.approvedBy()).isEqualTo(OWNER_ID);
        assertThat(view.active()).isTrue();
        assertThat(AlertSilence.isActive(jdbc, TASK_ID, Instant.now())).isTrue();
        assertThat(AlertSilence.isActive(jdbc, 5999L, Instant.now())).isFalse();
    }

    @Test
    @DisplayName("静默到期后不再抑制，且记录不被删除，可在列表中核验历史")
    void expiredSilenceStopsSuppressingButStaysAuditable() {
        AlertLifecycleService.SilenceView view = lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest("TASK", TASK_ID, "已结束的维护窗口",
                        LocalDateTime.now().minusHours(3), LocalDateTime.now().minusHours(1)));

        assertThat(view.active()).isFalse();
        assertThat(AlertSilence.isActive(jdbc, TASK_ID, Instant.now())).isFalse();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_silence WHERE id=?", Integer.class, view.id()))
                .isEqualTo(1);

        AlertLifecycleService.SilenceView listed = lifecycle.listSilences(OWNER).stream()
                .filter(item -> item.id() == view.id()).findFirst().orElseThrow();
        assertThat(listed.active()).isFalse();
        assertThat(listed.startsAt()).isNotNull();
        assertThat(listed.endsAt()).isNotNull();
    }

    @Test
    @DisplayName("撤销后可核验：记录消失且不再抑制告警")
    void cancelledSilenceIsVerifiablyGone() {
        long silenceId = lifecycle.createSilence(OWNER,
                new AlertLifecycleService.SilenceRequest("GLOBAL", null, "临时静默",
                        LocalDateTime.now().minusMinutes(1), LocalDateTime.now().plusHours(4))).id();
        assertThat(AlertSilence.isActive(jdbc, TASK_ID, Instant.now())).isTrue();

        lifecycle.cancelSilence(OWNER, silenceId);

        assertThat(AlertSilence.isActive(jdbc, TASK_ID, Instant.now())).isFalse();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_silence WHERE id=?", Integer.class, silenceId))
                .isZero();
        assertThatThrownBy(() -> lifecycle.cancelSilence(OWNER, silenceId))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("不存在");
    }
}
