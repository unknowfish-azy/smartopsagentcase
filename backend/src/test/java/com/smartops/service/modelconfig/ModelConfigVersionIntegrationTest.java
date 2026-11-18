package com.smartops.service.modelconfig;

import com.fasterxml.jackson.databind.JsonNode;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.exception.BusinessException;
import com.smartops.service.ModelRouterService;
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
 * 模型网关控制面：版本发布、快照生效、回滚与闸门拦截。
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:model_config_cp;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.model.control-plane.refresh-ms=3600000",
        "smartops.model.control-plane.initial-delay-ms=3600000",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class ModelConfigVersionIntegrationTest {

    private static final long OWNER = 501L;
    private static final long CONNECTION_A = 9001L;
    private static final long CONNECTION_B = 9002L;
    private static final long GROUP_ID = 9100L;
    private static final long ROUTE_ID = 9200L;

    @Autowired JdbcTemplate jdbc;
    @Autowired ModelConfigVersionService versions;
    @Autowired ModelConfigRegistry registry;
    @Autowired ModelRouterService router;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM model_gateway_config_version");
        jdbc.update("DELETE FROM model_gateway_route");
        jdbc.update("DELETE FROM model_gateway_group");
        jdbc.update("DELETE FROM model_connections");
        registry.refreshIfChanged();

        connection(CONNECTION_A, "conn-a", "model-a");
        connection(CONNECTION_B, "conn-b", "model-b");
        jdbc.update("INSERT INTO model_gateway_group(id,owner_user_id,name,slug,scope,enabled,route_mode) "
                + "VALUES(?,?,?,?,?,?,?)", GROUP_ID, OWNER, "运维默认组", "ops", "PERSONAL", true, "MANUAL");
        jdbc.update("INSERT INTO model_gateway_route(id,group_id,connection_id,priority,weight,enabled) "
                + "VALUES(?,?,?,?,?,?)", ROUTE_ID, GROUP_ID, CONNECTION_A, 1, 100, true);
    }

    @Test
    @DisplayName("发布后网关按快照路由，工作区改动不立即影响生效版本")
    void publishActivatesSnapshotAndWorkingCopyChangesStayStaged() {
        Map<String, Object> draft = versions.createDraft(1L, "首次发布");
        assertThat(draft.get("status")).isEqualTo("DRAFT");
        // 首次发布：1 个模型组 + 2 条连接相对空配置都是新增
        assertThat(((JsonNode) draft.get("diff")).get("count").asInt()).isEqualTo(3);

        Map<String, Object> active = versions.activate(((Number) draft.get("id")).longValue(), 1L);
        assertThat(active.get("status")).isEqualTo("ACTIVE");
        assertThat(registry.currentVersion()).isEqualTo(((Number) active.get("version")).intValue());

        assertThat(selectedConnection()).isEqualTo(CONNECTION_A);

        // 只改工作区，不发布：仍然走快照里的旧连接
        jdbc.update("UPDATE model_gateway_route SET connection_id=? WHERE id=?", CONNECTION_B, ROUTE_ID);
        assertThat(selectedConnection()).isEqualTo(CONNECTION_A);

        // 发布后才切到新连接
        Map<String, Object> next = versions.createDraft(1L, "切到 conn-b");
        assertThat(((JsonNode) next.get("diff")).get("count").asInt()).isEqualTo(1);
        versions.activate(((Number) next.get("id")).longValue(), 1L);
        assertThat(selectedConnection()).isEqualTo(CONNECTION_B);
    }

    @Test
    @DisplayName("回滚以历史内容新建版本，不改写历史")
    void rollbackCreatesNewVersionFromHistory() {
        Map<String, Object> first = versions.createDraft(1L, "v1 使用 conn-a");
        long firstId = ((Number) first.get("id")).longValue();
        versions.activate(firstId, 1L);

        jdbc.update("UPDATE model_gateway_route SET connection_id=? WHERE id=?", CONNECTION_B, ROUTE_ID);
        Map<String, Object> second = versions.createDraft(1L, "v2 使用 conn-b");
        versions.activate(((Number) second.get("id")).longValue(), 1L);
        assertThat(selectedConnection()).isEqualTo(CONNECTION_B);

        Map<String, Object> rolledBack = versions.rollback(firstId, 1L, "上游异常");
        assertThat(rolledBack.get("status")).isEqualTo("ACTIVE");
        assertThat(rolledBack.get("summary")).asString().contains("回滚至");
        assertThat(selectedConnection()).isEqualTo(CONNECTION_A);

        List<Map<String, Object>> history = versions.list(20);
        assertThat(history).hasSize(3);
        assertThat(history.get(0).get("status")).isEqualTo("ACTIVE");
        assertThat(history).filteredOn(row -> "SUPERSEDED".equals(row.get("status"))).hasSize(2);
    }

    @Test
    @DisplayName("工作区与生效版本一致时拒绝生成空版本")
    void unchangedWorkingCopyIsRejected() {
        Map<String, Object> draft = versions.createDraft(1L, "首次发布");
        versions.activate(((Number) draft.get("id")).longValue(), 1L);

        assertThatThrownBy(() -> versions.createDraft(1L, "重复发布"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("没有可发布的变更");
    }

    @Test
    @DisplayName("闸门拦截没有可用路由的配置发布")
    void gateBlocksReleaseWithoutUsableRoute() {
        jdbc.update("UPDATE model_gateway_route SET enabled=FALSE WHERE id=?", ROUTE_ID);
        Map<String, Object> draft = versions.createDraft(1L, "禁用全部路由");
        assertThat(draft.get("status")).isEqualTo("DRAFT");
        assertThat(((JsonNode) draft.get("gate")).get("passed").asBoolean()).isFalse();

        long id = ((Number) draft.get("id")).longValue();
        assertThatThrownBy(() -> versions.activate(id, 1L))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("配置校验未通过");
        assertThat(registry.currentVersion()).isNull();
    }

    @Test
    @DisplayName("灰度发布只让部分用户走新版本，转全量后全部切换")
    void canaryReleaseSplitsTrafficAndPromotes() {
        Map<String, Object> first = versions.createDraft(1L, "v1 全量");
        versions.activate(((Number) first.get("id")).longValue(), 1L);

        jdbc.update("UPDATE model_gateway_route SET connection_id=? WHERE id=?", CONNECTION_B, ROUTE_ID);
        Map<String, Object> second = versions.createDraft(1L, "v2 灰度");
        long secondId = ((Number) second.get("id")).longValue();

        // 比例必须在 1-100
        assertThatThrownBy(() -> versions.activate(secondId, 1L, 0))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("灰度比例");
        assertThatThrownBy(() -> versions.activate(secondId, 1L, 101))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("灰度比例");

        Map<String, Object> canary = versions.activate(secondId, 1L, 40);
        assertThat(canary.get("status")).isEqualTo("ACTIVE");
        assertThat(canary.get("rolloutPercent")).isEqualTo(40);
        // 全量版本仍是 v1，灰度版本 v2 负责 40% 流量
        assertThat(registry.currentVersion()).isEqualTo(1);
        assertThat(registry.canaryVersion()).isEqualTo(2);
        assertThat(registry.canaryPercent()).isEqualTo(40);

        Long canaryOwner = null;
        Long stableOwner = null;
        for (long owner = 1; owner <= 500 && (canaryOwner == null || stableOwner == null); owner++) {
            if (ModelConfigRegistry.bucket(owner, "ops") < 40 && canaryOwner == null) {
                canaryOwner = owner;
            } else if (ModelConfigRegistry.bucket(owner, "ops") >= 40 && stableOwner == null) {
                stableOwner = owner;
            }
        }
        assertThat(canaryOwner).isNotNull();
        assertThat(stableOwner).isNotNull();
        assertThat(registry.resolve(canaryOwner, "ops").version()).isEqualTo(2);
        assertThat(registry.resolve(stableOwner, "ops").version()).isEqualTo(1);
        // 审计归因与路由分桶必须一致
        assertThat(registry.resolveVersion(canaryOwner, "ops")).isEqualTo(2);
        assertThat(registry.resolveVersion(stableOwner, "ops")).isEqualTo(1);

        versions.promote(secondId, 1L);
        assertThat(registry.currentVersion()).isEqualTo(2);
        assertThat(registry.canaryVersion()).isNull();
        assertThat(selectedConnection()).isEqualTo(CONNECTION_B);
        assertThat(versions.get(secondId).get("rolloutPercent")).isEqualTo(100);
    }

    @Test
    @DisplayName("没有全量生效版本时不能直接灰度")
    void canaryRequiresAnActiveFullRelease() {
        Map<String, Object> draft = versions.createDraft(1L, "首次即灰度");
        long id = ((Number) draft.get("id")).longValue();
        assertThatThrownBy(() -> versions.activate(id, 1L, 30))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("灰度发布需要已有全量生效版本");
    }

    @Test
    @DisplayName("只有草稿可以删除，已发布版本必须保留审计记录")
    void onlyDraftCanBeDeleted() {
        Map<String, Object> draft = versions.createDraft(1L, "首次发布");
        long id = ((Number) draft.get("id")).longValue();
        versions.activate(id, 1L);

        assertThatThrownBy(() -> versions.delete(id))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("只能删除草稿");
    }

    private Long selectedConnection() {
        var request = new ModelInvocationRequest();
        request.setPrompt("帮我看下 web-01 的 CPU");
        var routed = router.selectConnections("ops", OWNER, request);
        assertThat(routed).isNotEmpty();
        return routed.get(0).connectionId();
    }

    private void connection(long id, String name, String modelName) {
        jdbc.update("INSERT INTO model_connections"
                        + "(id,user_id,name,provider,base_url,model_name,api_key_ciphertext,api_key_last4,enabled,timeout_seconds) "
                        + "VALUES(?,?,?,?,?,?,?,?,?,?)",
                id, OWNER, name, "openai-compatible", "https://example.test/v1", modelName,
                "ciphertext", "1234", true, 60);
    }
}
