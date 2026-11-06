package com.smartops.integration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.smartops.exception.BusinessException;
import com.smartops.recovery.RecoveryContractService;
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
 * 恢复契约平台侧的持久化与准入校验（真实迁移脚本 + 真实 SQL + H2）。
 *
 * <<p>这里只验证"平台不做假"的部分：归属过滤、幂等、回执不变式、越权按 404。
 * 三值判定与回放计算不在此处重复实现，也不在这里伪造 verdict。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:recovery_contract;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE"
})
class RecoveryContractIntegrationTest {

    private static final long OWNER = 81L;
    private static final long OTHER = 82L;
    private static final long RUN_ID = 9001L;

    @Autowired RecoveryContractService service;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper json;

    @BeforeEach
    void seed() {
        for (String table : List.of("recovery_replay_bundle_record", "recovery_receipt_record",
                "recovery_observation_record", "recovery_contract_record", "operation_run_record")) {
            jdbc.update("DELETE FROM " + table);
        }
        jdbc.update("INSERT INTO operation_run_record(id,trace_id,user_id,runtime_id,tool_id,status,started_at) "
                + "VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)", RUN_ID, "trace-9001", OWNER, "runtime-1", "ops.diagnose", "SUCCEEDED");
    }

    @Test
    @DisplayName("同一幂等键 + 同一 digest 视为重放，不重复建契约")
    void createIsIdempotentForSameDigest() {
        Map<String, Object> first = service.create(createBody("key-1", "sha256:" + "a".repeat(64)));
        Map<String, Object> second = service.create(createBody("key-1", "sha256:" + "a".repeat(64)));

        assertThat(second.get("id")).isEqualTo(first.get("id"));
        assertThat(second.get("idempotentReplay")).isEqualTo(true);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM recovery_contract_record", Integer.class)).isEqualTo(1);
    }

    @Test
    @DisplayName("同一幂等键 + 不同 digest 冲突，不静默覆盖")
    void createRejectsSameKeyDifferentDigest() {
        service.create(createBody("key-2", "sha256:" + "a".repeat(64)));

        assertThatThrownBy(() -> service.create(createBody("key-2", "sha256:" + "b".repeat(64))))
                .isInstanceOf(BusinessException.class)
                .satisfies(error -> assertThat(((BusinessException) error).getCode()).isEqualTo(409));
    }

    @Test
    @DisplayName("契约不能引用别人的 run")
    void createRejectsRunOwnedByAnotherUser() {
        ObjectNode body = createBody("key-3", "sha256:" + "a".repeat(64));
        body.put("ownerUserId", OTHER);

        assertThatThrownBy(() -> service.create(body))
                .isInstanceOf(BusinessException.class)
                .satisfies(error -> assertThat(((BusinessException) error).getCode()).isEqualTo(400));
    }

    @Test
    @DisplayName("列表与详情只返回当前主体的契约，越权按 404")
    void detailHidesOtherUsersContract() {
        Map<String, Object> created = service.create(createBody("key-4", "sha256:" + "a".repeat(64)));
        Long id = ((Number) created.get("id")).longValue();

        Map<String, Object> mine = service.list(OWNER, null, 1, 20);
        assertThat((List<?>) mine.get("items")).hasSize(1);
        assertThat((List<?>) service.list(OTHER, null, 1, 20).get("items")).isEmpty();

        assertThatThrownBy(() -> service.detail(OTHER, id))
                .isInstanceOf(BusinessException.class)
                .satisfies(error -> assertThat(((BusinessException) error).getCode()).isEqualTo(404));
        assertThat(service.detail(OWNER, id).get("contract")).isNotNull();
    }

    @Test
    @DisplayName("回执不变式：只有 VERIFIED 才能 ACTIVE 且必须带有效期")
    void appendReceiptEnforcesVerifiedInvariant() {
        Long id = createdId("key-5");

        assertThatThrownBy(() -> service.appendReceipt(id, receiptBody(
                "CONTRADICTED", "ACTIVE", "\"2026-11-06T10:00:00Z\"", "\"2026-11-06T10:01:00Z\"")))
                .isInstanceOf(BusinessException.class)
                .satisfies(error -> assertThat(((BusinessException) error).getCode()).isEqualTo(400));

        assertThatThrownBy(() -> service.appendReceipt(id, receiptBody(
                "INSUFFICIENT", "NOT_ISSUED", "\"2026-11-06T10:00:00Z\"", "null")))
                .isInstanceOf(BusinessException.class)
                .satisfies(error -> assertThat(((BusinessException) error).getCode()).isEqualTo(400));

        assertThatThrownBy(() -> service.appendReceipt(id, receiptBody(
                "VERIFIED", "ACTIVE", "\"2026-11-06T10:00:00Z\"", "null")))
                .isInstanceOf(BusinessException.class)
                .satisfies(error -> assertThat(((BusinessException) error).getCode()).isEqualTo(400));

        Map<String, Object> ok = service.appendReceipt(id, receiptBody(
                "VERIFIED", "ACTIVE", "\"2026-11-06T10:00:00Z\"", "\"2026-11-06T10:01:00Z\""));
        assertThat(ok.get("receiptId")).isEqualTo("rcpt-1");
        assertThat(jdbc.queryForObject("SELECT receipt_state FROM recovery_receipt_record WHERE contract_record_id=?",
                String.class, id)).isEqualTo("ACTIVE");
    }

    @Test
    @DisplayName("重复观测 ID 不填补采样槽，直接拒绝")
    void appendObservationsRejectsDuplicateId() {
        Long id = createdId("key-6");

        Map<String, Object> accepted = service.appendObservations(id,
                tree("[" + observation("obs-1", 1) + "]"));
        assertThat(accepted.get("accepted")).isEqualTo(1);

        assertThatThrownBy(() -> service.appendObservations(id,
                tree("[" + observation("obs-1", 2) + "]")))
                .isInstanceOf(BusinessException.class)
                .satisfies(error -> assertThat(((BusinessException) error).getCode()).isEqualTo(409));
    }

    @Test
    @DisplayName("变形回放包不得标记为历史事实，且必须带 mutation_diff")
    void appendReplayBundleRejectsMislabelledMutation() {
        Long id = createdId("key-7");

        assertThatThrownBy(() -> service.appendReplayBundle(id, tree(
                "{\"bundle\":{\"bundle_id\":\"b2\",\"digest\":\"sha256:" + "c".repeat(64)
                        + "\",\"parent_bundle_id\":\"b1\",\"is_historical_fact\":true}}")))
                .isInstanceOf(BusinessException.class)
                .satisfies(error -> assertThat(((BusinessException) error).getCode()).isEqualTo(400));

        Map<String, Object> ok = service.appendReplayBundle(id, tree(
                "{\"bundle\":{\"bundle_id\":\"b2\",\"digest\":\"sha256:" + "c".repeat(64)
                        + "\",\"parent_bundle_id\":\"b1\",\"is_historical_fact\":false,"
                        + "\"mutation_diff\":{\"policy\":\"changed\"}},\"replay_result\":{\"verdict\":\"INSUFFICIENT\"}}"));
        assertThat(ok.get("bundleId")).isEqualTo("b2");
        assertThat(service.replay(OWNER, id).get("latest")).isNotNull();
    }

    // ---------------------------------------------------------------- helpers

    /** 测试里的 JSON 字面量都是写死的合法 JSON，失败即测试代码错误，不做线上式兜底。 */
    private JsonNode tree(String raw) {
        try {
            return json.readTree(raw);
        } catch (Exception malformed) {
            throw new IllegalStateException(malformed);
        }
    }

    private Long createdId(String key) {
        Map<String, Object> created = service.create(createBody(key, "sha256:" + "a".repeat(64)));
        return ((Number) created.get("id")).longValue();
    }

    private ObjectNode createBody(String key, String digest) {
        ObjectNode body = json.createObjectNode();
        body.put("ownerUserId", OWNER);
        body.put("runId", RUN_ID);
        body.put("idempotencyKey", key);
        body.set("contract", tree("""
                {"schema_version":"recovery-contract/v1","id":"ctr-%s","version":"1","scope":"prod/web",
                 "target":{"target_id":"prod-web-01","target_kind":"host"},
                 "expected_revision":"rev-1","digest":"%s","expires_after":600000,
                 "obligations":[{"id":"obl-health","required":true}],
                 "source_groups":["g1","g2"],"window":{"min_groups":3},
                 "budgets":{"max_probe_calls":12}}
                """.formatted(key, digest)));
        body.set("claim", tree("""
                {"id":"claim-%s","contract_digest":"%s","claim_type":"BUSINESS_RECOVERY",
                 "scope":"prod/web","target":{"target_id":"prod-web-01"},"expected_revision":"rev-1"}
                """.formatted(key, digest)));
        return body;
    }

    private JsonNode receiptBody(String verdict, String state, String issuedAt, String validUntil) {
        return tree("""
                {"receipt":{"id":"rcpt-1","run_id":"run-1","verification_round":1,"verdict":"%s",
                            "receipt_state":"%s","issued_at":%s,"valid_until":%s,
                            "policy_version":"recovery-contract/v1"},
                 "obligation_results":[{"obligation_id":"obl-health","value":"TRUE","reason_codes":[]}]}
                """.formatted(verdict, state, issuedAt, validUntil));
    }

    private String observation(String id, int sequence) {
        return """
                {"id":"%s","run_id":"run-1","verification_round":1,"collector_id":"probe-a",
                 "probe_id":"probe-a","source_group":"g1","observed_at":"2026-11-06T10:00:00Z",
                 "binding_revision":"rev-1","observed_revision":"rev-1","sequence":%d,
                 "elapsed_ms":120,"payload":{"status":"ok"}}
                """.formatted(id, sequence);
    }
}
