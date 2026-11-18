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
 * 模型网关控制面：多级审批（required-approvals=2）。
 *
 * <p>审批开启后草稿不能直接发布，必须由创建人以外的人逐级通过；
 * 达到级数后按申请的比例自动发布。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:model_config_approval;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.model.control-plane.refresh-ms=3600000",
        "smartops.model.control-plane.initial-delay-ms=3600000",
        "smartops.model.control-plane.required-approvals=2",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class ModelConfigApprovalIntegrationTest {

    private static final long CREATOR = 601L;
    private static final long APPROVER_A = 602L;
    private static final long APPROVER_B = 603L;
    private static final long CONNECTION_A = 9301L;
    private static final long CONNECTION_B = 9302L;
    private static final long GROUP_ID = 9400L;
    private static final long ROUTE_ID = 9500L;

    @Autowired JdbcTemplate jdbc;
    @Autowired ModelConfigVersionService versions;
    @Autowired ModelConfigRegistry registry;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM model_gateway_config_approval");
        jdbc.update("DELETE FROM model_gateway_config_version");
        jdbc.update("DELETE FROM model_gateway_route");
        jdbc.update("DELETE FROM model_gateway_group");
        jdbc.update("DELETE FROM model_connections");
        registry.refreshIfChanged();

        connection(CONNECTION_A, "conn-a", "model-a");
        connection(CONNECTION_B, "conn-b", "model-b");
        jdbc.update("INSERT INTO model_gateway_group(id,owner_user_id,name,slug,scope,enabled,route_mode) "
                + "VALUES(?,?,?,?,?,?,?)", GROUP_ID, CREATOR, "运维默认组", "ops", "PERSONAL", true, "MANUAL");
        jdbc.update("INSERT INTO model_gateway_route(id,group_id,connection_id,priority,weight,enabled) "
                + "VALUES(?,?,?,?,?,?)", ROUTE_ID, GROUP_ID, CONNECTION_A, 1, 100, true);
    }

    @Test
    @DisplayName("开启审批后不能直接发布，两级审批通过后自动生效")
    void releaseRequiresTwoApprovals() {
        long firstId = createDraft("首次发布");
        assertThatThrownBy(() -> versions.activate(firstId, CREATOR))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("请先提交审批");

        assertThatThrownBy(() -> versions.submit(firstId, CREATOR, 0))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("灰度比例");

        Map<String, Object> pending = versions.submit(firstId, CREATOR, 100);
        assertThat(pending.get("status")).isEqualTo("PENDING_APPROVAL");
        assertThat(pending.get("requestedPercent")).isEqualTo(100);
        assertThat(pending.get("requiredApprovals")).isEqualTo(2);

        // 创建人不能审批自己的版本
        assertThatThrownBy(() -> versions.approve(firstId, CREATOR, "自批"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("不能审批自己创建");

        Map<String, Object> firstApproval = versions.approve(firstId, APPROVER_A, "同意");
        assertThat(firstApproval.get("status")).isEqualTo("PENDING_APPROVAL");
        assertThat((List<?>) firstApproval.get("approvals")).hasSize(1);

        // 同一审批人不能重复审批
        assertThatThrownBy(() -> versions.approve(firstId, APPROVER_A, "再同意一次"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("已经审批过");

        Map<String, Object> released = versions.approve(firstId, APPROVER_B, "同意");
        assertThat(released.get("status")).isEqualTo("ACTIVE");
        assertThat(released.get("rolloutPercent")).isEqualTo(100);
        assertThat(registry.currentVersion()).isEqualTo(1);
    }

    @Test
    @DisplayName("审批通过的灰度版本按申请比例生效，可转全量")
    void approvedCanaryUsesRequestedPercent() {
        long fullId = createDraft("v1 全量");
        versions.submit(fullId, CREATOR, 100);
        versions.approve(fullId, APPROVER_A, null);
        versions.approve(fullId, APPROVER_B, null);
        assertThat(registry.currentVersion()).isEqualTo(1);

        jdbc.update("UPDATE model_gateway_route SET connection_id=? WHERE id=?", CONNECTION_B, ROUTE_ID);
        long canaryId = createDraft("v2 灰度 30%");
        versions.submit(canaryId, CREATOR, 30);
        Map<String, Object> released = versions.approve(canaryId, APPROVER_A, null);
        assertThat(released.get("status")).isEqualTo("PENDING_APPROVAL");
        released = versions.approve(canaryId, APPROVER_B, null);
        assertThat(released.get("status")).isEqualTo("ACTIVE");
        assertThat(released.get("rolloutPercent")).isEqualTo(30);
        assertThat(registry.currentVersion()).isEqualTo(1);
        assertThat(registry.canaryVersion()).isEqualTo(2);

        versions.promote(canaryId, CREATOR);
        assertThat(registry.currentVersion()).isEqualTo(2);
        assertThat(registry.canaryVersion()).isNull();
    }

    @Test
    @DisplayName("驳回后版本不可发布，可删除；重新生成草稿才能再次提交")
    void rejectedVersionIsTerminalUntilRedrafted() {
        long id = createDraft("待驳回");
        versions.submit(id, CREATOR, 100);
        Map<String, Object> rejected = versions.reject(id, APPROVER_A, "变更窗口不对");
        assertThat(rejected.get("status")).isEqualTo("REJECTED");
        assertThat(rejected.get("rejectionComment")).isEqualTo("变更窗口不对");
        assertThat((List<?>) rejected.get("approvals")).hasSize(1);

        assertThatThrownBy(() -> versions.submit(id, CREATOR, 100))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("只有草稿版本可以提交审批");
        assertThat(registry.currentVersion()).isNull();

        versions.delete(id);
        assertThat(versions.list(10)).isEmpty();
    }

    @Test
    @DisplayName("灰度健康对比按版本聚合真实调用：样本不足不出结论，失败偏高建议回滚")
    void compareUsesRealInvocationsPerVersion() {
        long fullId = createDraft("v1 全量");
        versions.submit(fullId, CREATOR, 100);
        versions.approve(fullId, APPROVER_A, null);
        versions.approve(fullId, APPROVER_B, null);

        jdbc.update("UPDATE model_gateway_route SET connection_id=? WHERE id=?", CONNECTION_B, ROUTE_ID);
        long canaryId = createDraft("v2 灰度 30%");
        versions.submit(canaryId, CREATOR, 30);
        versions.approve(canaryId, APPROVER_A, null);
        versions.approve(canaryId, APPROVER_B, null);

        for (int index = 0; index < 3; index++) {
            invocation(index, 1, "SUCCESS", 100);
        }
        Map<String, Object> sparse = versions.compare(canaryId, 60);
        assertThat(sparse.get("verdict")).isEqualTo("INSUFFICIENT_DATA");
        assertThat((List<?>) sparse.get("reasons")).isNotEmpty();

        for (int index = 0; index < 30; index++) {
            invocation(10 + index, 1, "SUCCESS", 100);
            invocation(50 + index, 2, "SUCCESS", 110);
        }
        Map<String, Object> healthy = versions.compare(canaryId, 60);
        assertThat(healthy.get("verdict")).isEqualTo("PROMOTE");
        assertThat(healthy.get("stableVersion")).isEqualTo(1);
        assertThat(((Map<?, ?>) healthy.get("canary")).get("calls")).isEqualTo(30L);
        assertThat(((Map<?, ?>) healthy.get("canary")).get("successRate")).isEqualTo(100.0);
        assertThat(((Map<?, ?>) healthy.get("stable")).get("calls")).isEqualTo(33L);

        jdbc.update("DELETE FROM model_gateway_invocation WHERE config_version=2");
        for (int index = 0; index < 20; index++) {
            invocation(100 + index, 2, "FAILED", 300);
        }
        for (int index = 0; index < 10; index++) {
            invocation(130 + index, 2, "SUCCESS", 300);
        }
        Map<String, Object> bad = versions.compare(canaryId, 60);
        assertThat(bad.get("verdict")).isEqualTo("ROLLBACK");
        assertThat(((Map<?, ?>) bad.get("canary")).get("successRate")).isEqualTo(33.3);
    }

    private void invocation(long id, int configVersion, String status, long durationMs) {
        jdbc.update("INSERT INTO model_gateway_invocation"
                        + "(id,key_id,group_slug,model_name,config_version,status,duration_ms,total_tokens) "
                        + "VALUES(?,?,?,?,?,?,?,?)",
                id, null, "ops", "model-a", configVersion, status, durationMs, 10L);
    }

    private long createDraft(String summary) {
        return ((Number) versions.createDraft(CREATOR, summary).get("id")).longValue();
    }

    private void connection(long id, String name, String modelName) {
        jdbc.update("INSERT INTO model_connections"
                        + "(id,user_id,name,provider,base_url,model_name,api_key_ciphertext,api_key_last4,enabled,timeout_seconds) "
                        + "VALUES(?,?,?,?,?,?,?,?,?,?)",
                id, CREATOR, name, "openai-compatible", "https://example.test/v1", modelName,
                "ciphertext", "1234", true, 60);
    }
}
