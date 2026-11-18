package com.smartops.service.modelconfig;

import com.smartops.exception.BusinessException;
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
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * 控制面：审批人白名单与审批通知。
 *
 * <p>配置 approvers 后只有名单内的账号可审批，提交与审批结果会写入
 * team_notification，供现有通知中心展示。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:model_config_approver;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.model.control-plane.refresh-ms=3600000",
        "smartops.model.control-plane.initial-delay-ms=3600000",
        "smartops.model.control-plane.required-approvals=1",
        "smartops.model.control-plane.approvers=alice,bob",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class ModelConfigApproverScopeTest {

    private static final long CREATOR = 9700L;
    private static final long ALICE = 9701L;
    private static final long BOB = 9702L;
    private static final long CAROL = 9703L;
    private static final long CONNECTION_A = 9711L;
    private static final long CONNECTION_B = 9712L;
    private static final long GROUP_ID = 9720L;
    private static final long ROUTE_ID = 9730L;

    @Autowired JdbcTemplate jdbc;
    @Autowired ModelConfigVersionService versions;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM model_gateway_config_approval");
        jdbc.update("DELETE FROM model_gateway_config_version");
        jdbc.update("DELETE FROM model_gateway_route");
        jdbc.update("DELETE FROM model_gateway_group");
        jdbc.update("DELETE FROM model_connections");
        jdbc.update("DELETE FROM team_notification WHERE reference_id LIKE 'model-config:%'");
        jdbc.update("DELETE FROM app_user WHERE id IN (?,?,?,?)", CREATOR, ALICE, BOB, CAROL);

        user(CREATOR, "creator");
        user(ALICE, "alice");
        user(BOB, "bob");
        user(CAROL, "carol");

        connection(CONNECTION_A, "conn-a");
        connection(CONNECTION_B, "conn-b");
        jdbc.update("INSERT INTO model_gateway_group(id,owner_user_id,name,slug,scope,enabled,route_mode) "
                + "VALUES(?,?,?,?,?,?,?)", GROUP_ID, CREATOR, "运维默认组", "ops", "PERSONAL", true, "MANUAL");
        jdbc.update("INSERT INTO model_gateway_route(id,group_id,connection_id,priority,weight,enabled) "
                + "VALUES(?,?,?,?,?,?)", ROUTE_ID, GROUP_ID, CONNECTION_A, 1, 100, true);
    }

    @Test
    @DisplayName("只有白名单内的审批人可以审批，提交与结果都会通知相关人")
    void onlyListedApproversCanApproveAndNotificationsAreSent() {
        long id = createDraft("白名单审批");
        versions.submit(id, CREATOR, 100);

        List<Map<String, Object>> pending = jdbc.queryForList(
                "SELECT user_id,message FROM team_notification WHERE reference_id=? ORDER BY user_id",
                "model-config:" + id);
        assertThat(pending).extracting(row -> ((Number) row.get("user_id")).longValue())
                .containsExactly(ALICE, BOB);

        assertThatThrownBy(() -> versions.approve(id, CAROL, "我也想批"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("不在模型配置审批人名单内");

        Map<String, Object> released = versions.approve(id, ALICE, "同意");
        assertThat(released.get("status")).isEqualTo("ACTIVE");

        List<Map<String, Object>> toCreator = jdbc.queryForList(
                "SELECT notification_type,message FROM team_notification WHERE user_id=? AND reference_id=?",
                CREATOR, "model-config:" + id);
        assertThat(toCreator).singleElement().satisfies(row -> {
            assertThat(row.get("notification_type")).isEqualTo("MODEL_CONFIG_APPROVAL");
            assertThat(String.valueOf(row.get("message"))).contains("已通过审批");
        });
    }

    @Test
    @DisplayName("驳回后创建人收到带原因的驳回通知")
    void rejectionNotifiesCreatorWithReason() {
        jdbc.update("UPDATE model_gateway_route SET connection_id=? WHERE id=?", CONNECTION_B, ROUTE_ID);
        long id = createDraft("待驳回");
        versions.submit(id, CREATOR, 100);
        versions.reject(id, BOB, "变更窗口不对");

        List<Map<String, Object>> toCreator = jdbc.queryForList(
                "SELECT message FROM team_notification WHERE user_id=? AND reference_id=?",
                CREATOR, "model-config:" + id);
        assertThat(toCreator).singleElement()
                .satisfies(row -> assertThat(String.valueOf(row.get("message"))).contains("被驳回", "变更窗口不对"));
    }

    private long createDraft(String summary) {
        return ((Number) versions.createDraft(CREATOR, summary).get("id")).longValue();
    }

    private void user(long id, String username) {
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role,enabled) VALUES(?,?,?,?,?)",
                id, username, "x", "admin", true);
    }

    private void connection(long id, String name) {
        jdbc.update("INSERT INTO model_connections"
                        + "(id,user_id,name,provider,base_url,model_name,api_key_ciphertext,api_key_last4,enabled,timeout_seconds) "
                        + "VALUES(?,?,?,?,?,?,?,?,?,?)",
                id, CREATOR, name, "openai-compatible", "https://example.test/v1", "model-a",
                "ciphertext", "1234", true, 60);
    }
}
