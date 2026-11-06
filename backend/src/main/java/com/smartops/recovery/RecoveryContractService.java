package com.smartops.recovery;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.entity.RecoveryContractRecord;
import com.smartops.entity.RecoveryObservationRecord;
import com.smartops.entity.RecoveryReceiptRecord;
import com.smartops.entity.RecoveryReplayBundleRecord;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.RecoveryContractMapper;
import com.smartops.mapper.RecoveryObservationMapper;
import com.smartops.mapper.RecoveryReceiptMapper;
import com.smartops.mapper.RecoveryReplayBundleMapper;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 恢复契约 v1 的平台侧读写服务。
 *
 * <p>职责边界（platform-integration §2.4）：平台只做<b>持久化 + 归属过滤 + 契约语义的准入校验</b>，
 * 不重新计算 verdict、不签发回执、不放宽时间或授权。三值判定在 Python 侧
 * {@code agent/recovery_contracts} 完成，本服务只保存其结果。</p>
 *
 * <p>归属：浏览器读路径的 {@code ownerUserId} 必须来自认证上下文（SessionUser），
 * 绝不采信客户端自述身份；内部写路径由 agent 显式给出并在写入前校验 run 归属。</p>
 */
@Service
public class RecoveryContractService {

    private static final int MAX_PAGE_SIZE = 100;
    private static final List<String> RECEIPT_STATES = List.of("NOT_ISSUED", "ACTIVE", "INVALIDATED", "EXPIRED");

    private final RecoveryContractMapper contracts;
    private final RecoveryObservationMapper observations;
    private final RecoveryReceiptMapper receipts;
    private final RecoveryReplayBundleMapper bundles;
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    public RecoveryContractService(RecoveryContractMapper contracts,
                                   RecoveryObservationMapper observations,
                                   RecoveryReceiptMapper receipts,
                                   RecoveryReplayBundleMapper bundles,
                                   JdbcTemplate jdbc,
                                   ObjectMapper json) {
        this.contracts = contracts;
        this.observations = observations;
        this.receipts = receipts;
        this.bundles = bundles;
        this.jdbc = jdbc;
        this.json = json;
    }

    // ---------------------------------------------------------------- 浏览器读

    /** 列表：只返回当前主体名下的契约，附带最新一张回执的摘要。 */
    public Map<String, Object> list(Long ownerUserId, Long runId, int page, int pageSize) {
        int size = pageSize <= 0 ? 20 : Math.min(pageSize, MAX_PAGE_SIZE);
        int current = page <= 0 ? 1 : page;
        List<RecoveryContractRecord> rows = contracts.search(ownerUserId, runId, (current - 1) * size, size);
        List<Map<String, Object>> items = new ArrayList<>(rows.size());
        for (RecoveryContractRecord row : rows) {
            items.add(summary(row, receipts.findLatest(row.getId())));
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("items", items);
        result.put("page", current);
        result.put("pageSize", size);
        result.put("total", contracts.count(ownerUserId, runId));
        return result;
    }

    /** 详情：契约 + 最新回执 + 全部观测 + 回放包。越权按 404，不泄露存在性。 */
    public Map<String, Object> detail(Long ownerUserId, Long id) {
        RecoveryContractRecord contract = requireOwned(ownerUserId, id);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("summary", summary(contract, receipts.findLatest(id)));
        result.put("contract", readJson(contract.getContractJson()));
        result.put("claim", readJson(contract.getClaimJson()));
        RecoveryReceiptRecord latest = receipts.findLatest(id);
        result.put("receipt", latest == null ? null : receiptView(latest));
        List<Map<String, Object>> observationViews = new ArrayList<>();
        for (RecoveryObservationRecord observation : observations.findByContract(id)) {
            observationViews.add(observationView(observation));
        }
        result.put("observations", observationViews);
        List<Map<String, Object>> replayViews = new ArrayList<>();
        for (RecoveryReplayBundleRecord bundle : bundles.listByContract(id)) {
            replayViews.add(replayView(bundle));
        }
        result.put("replays", replayViews);
        return result;
    }

    /** 回放：返回该契约已登记的全部回放包与最新一次回放结果。 */
    public Map<String, Object> replay(Long ownerUserId, Long id) {
        requireOwned(ownerUserId, id);
        List<Map<String, Object>> bundleViews = new ArrayList<>();
        for (RecoveryReplayBundleRecord bundle : bundles.listByContract(id)) {
            bundleViews.add(replayView(bundle));
        }
        RecoveryReplayBundleRecord latest = bundles.findLatest(id);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("bundles", bundleViews);
        result.put("latest", latest == null ? null : replayView(latest));
        return result;
    }

    // ---------------------------------------------------------------- 内部写入

    /**
     * 登记契约。{@code idempotencyKey} 必填；同键同 digest 视为幂等重放返回既有记录，
     * 同键不同 digest 视为冲突（409），不静默覆盖。
     */
    @Transactional
    public Map<String, Object> create(JsonNode body) {
        long ownerUserId = requireLong(body, "ownerUserId");
        long runId = requireLong(body, "runId");
        String idempotencyKey = requireText(body, "idempotencyKey");
        JsonNode contract = body.get("contract");
        JsonNode claim = body.get("claim");
        if (contract == null || !contract.isObject()) {
            throw new BusinessException(400, "contract 必须是非空对象");
        }
        if (claim == null || !claim.isObject()) {
            throw new BusinessException(400, "claim 必须是非空对象");
        }

        // 契约必须绑定到一条真实存在、且属于该主体的运行记录；不凭空引用 run。
        Long runOwner = jdbc.query(
                "SELECT user_id FROM operation_run_record WHERE id=?",
                rs -> rs.next() ? rs.getLong(1) : null, runId);
        if (runOwner == null) {
            throw new BusinessException(400, "run_id 指向的运行记录不存在: " + runId);
        }
        if (runOwner != ownerUserId) {
            throw new BusinessException(400, "run_id 归属与 ownerUserId 不一致");
        }

        String contractId = requireText(contract, "id");
        String contractVersion = requireText(contract, "version");
        String digest = requireText(contract, "digest");
        String scope = requireText(contract, "scope");
        String expectedRevision = requireText(contract, "expected_revision");
        JsonNode target = contract.get("target");
        if (target == null || !target.isObject()) {
            throw new BusinessException(400, "contract.target 必须是非空对象");
        }
        String targetId = requireText(target, "target_id");

        Long expiresAfterMs = null;
        if (contract.hasNonNull("expires_after")) {
            expiresAfterMs = contract.get("expires_after").asLong();
        }

        RecoveryContractRecord existing = contracts.findByIdempotencyKey(ownerUserId, idempotencyKey);
        if (existing != null) {
            if (existing.getDigest().equals(digest)) {
                return createdView(existing, true);
            }
            throw new BusinessException(409, "幂等键已用于另一份契约（digest 不同）");
        }

        RecoveryContractRecord record = new RecoveryContractRecord();
        record.setContractId(contractId);
        record.setContractVersion(contractVersion);
        record.setRunId(runId);
        record.setOwnerUserId(ownerUserId);
        record.setIdempotencyKey(idempotencyKey);
        record.setScope(scope);
        record.setTargetId(targetId);
        record.setTargetKind(target.hasNonNull("target_kind") ? target.get("target_kind").asText() : null);
        record.setExpectedRevision(expectedRevision);
        record.setDigest(digest);
        record.setContractJson(toJson(contract));
        record.setClaimJson(toJson(claim));
        record.setExpiresAfterMs(expiresAfterMs == null ? 0L : expiresAfterMs);
        record.setValidFrom(body.hasNonNull("validFrom") ? body.get("validFrom").asText()
                : (contract.hasNonNull("valid_from") ? contract.get("valid_from").asText() : Instant.now().toString()));

        try {
            contracts.insert(record);
        } catch (DuplicateKeyException duplicate) {
            // 并发下同 digest/幂等键重复：按既有记录返回，仍然不覆盖
            RecoveryContractRecord again = contracts.findByIdempotencyKey(ownerUserId, idempotencyKey);
            if (again != null && again.getDigest().equals(digest)) {
                return createdView(again, true);
            }
            throw new BusinessException(409, "契约 digest 或幂等键重复");
        }
        return createdView(record, false);
    }

    /** 追加观测。重复 observationId 由唯一约束拒绝，不静默去重后继续采样。 */
    @Transactional
    public Map<String, Object> appendObservations(Long contractRecordId, JsonNode observationsBody) {
        RecoveryContractRecord contract = requireExisting(contractRecordId);
        JsonNode items = observationsBody.isArray() ? observationsBody : observationsBody.get("observations");
        if (items == null || !items.isArray() || items.isEmpty()) {
            throw new BusinessException(400, "observations 必须是非空数组");
        }
        int accepted = 0;
        List<String> rejected = new ArrayList<>();
        for (JsonNode item : items) {
            try {
                RecoveryObservationRecord record = toObservation(contractRecordId, contract, item);
                observations.insert(record);
                accepted++;
            } catch (DuplicateKeyException duplicate) {
                rejected.add(item.path("id").asText(""));
            }
        }
        if (!rejected.isEmpty()) {
            throw new BusinessException(409,
                    "重复观测 ID 被拒绝（不填补采样槽）: " + String.join(",", rejected));
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("contractRecordId", contractRecordId);
        result.put("accepted", accepted);
        return result;
    }

    /**
     * 追加回执。这里强制 semantics §7 的不变式：只有 VERIFIED 才能 ACTIVE 且带有效期；
     * 其余 verdict 一律 NOT_ISSUED 且 issued_at/valid_until 为空。不一致直接 400，不修正、不补签。
     */
    @Transactional
    public Map<String, Object> appendReceipt(Long contractRecordId, JsonNode body) {
        requireExisting(contractRecordId);
        JsonNode receipt = body.get("receipt");
        if (receipt == null || !receipt.isObject()) {
            throw new BusinessException(400, "receipt 必须是非空对象");
        }
        String receiptId = requireText(receipt, "id");
        String verdict = requireText(receipt, "verdict");
        String state = requireText(receipt, "receipt_state");
        if (!RECEIPT_STATES.contains(state)) {
            throw new BusinessException(400, "receipt_state 非法: " + state);
        }
        boolean verified = "VERIFIED".equals(verdict);
        boolean issued = "ACTIVE".equals(state);
        if (verified != issued) {
            throw new BusinessException(400,
                    "回执状态与判定不一致：VERIFIED 才能 ACTIVE，其余必须 NOT_ISSUED");
        }
        String issuedAt = textOrNull(receipt, "issued_at");
        String validUntil = textOrNull(receipt, "valid_until");
        if (verified && (issuedAt == null || validUntil == null)) {
            throw new BusinessException(400, "ACTIVE 回执必须同时给出 issued_at 与 valid_until");
        }
        if (!verified && (issuedAt != null || validUntil != null)) {
            throw new BusinessException(400, "非 VERIFIED 回执不得带 issued_at/valid_until");
        }

        RecoveryReceiptRecord record = new RecoveryReceiptRecord();
        record.setContractRecordId(contractRecordId);
        record.setReceiptId(receiptId);
        record.setRunId(requireText(receipt, "run_id"));
        record.setVerificationRound(receipt.path("verification_round").asInt(1));
        record.setVerdict(verdict);
        record.setReceiptState(state);
        record.setIssuedAt(issuedAt);
        record.setValidUntil(validUntil);
        record.setEvidenceSnapshotDigest(textOrNull(receipt, "evidence_snapshot_digest"));
        record.setPolicyVersion(receipt.path("policy_version").asText("recovery-contract/v1"));
        record.setReceiptJson(toJson(receipt));
        record.setObligationResultsJson(body.hasNonNull("obligation_results")
                ? toJson(body.get("obligation_results")) : "[]");
        record.setProbeDecisionJson(body.hasNonNull("probe_decision")
                ? toJson(body.get("probe_decision")) : null);
        record.setInvalidationEventsJson(body.hasNonNull("invalidation_events")
                ? toJson(body.get("invalidation_events")) : "[]");
        try {
            receipts.insert(record);
        } catch (DuplicateKeyException duplicate) {
            throw new BusinessException(409, "回执已存在，不得覆盖: " + receiptId);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("contractRecordId", contractRecordId);
        result.put("receiptId", receiptId);
        return result;
    }

    /** 追加回放包。变形包必须保留 parent 与 mutation_diff，且不得标为历史事实。 */
    @Transactional
    public Map<String, Object> appendReplayBundle(Long contractRecordId, JsonNode body) {
        requireExisting(contractRecordId);
        JsonNode bundle = body.get("bundle");
        if (bundle == null || !bundle.isObject()) {
            throw new BusinessException(400, "bundle 必须是非空对象");
        }
        String bundleId = requireText(bundle, "bundle_id");
        String digest = requireText(bundle, "digest");
        String parentBundleId = textOrNull(bundle, "parent_bundle_id");
        boolean historical = bundle.path("is_historical_fact").asBoolean(true);
        if (parentBundleId != null) {
            if (historical) {
                throw new BusinessException(400, "变形回放包不得标记为历史事实");
            }
            if (!bundle.hasNonNull("mutation_diff")) {
                throw new BusinessException(400, "变形回放包必须给出 mutation_diff");
            }
        }

        RecoveryReplayBundleRecord record = new RecoveryReplayBundleRecord();
        record.setContractRecordId(contractRecordId);
        record.setBundleId(bundleId);
        record.setParentBundleId(parentBundleId);
        record.setHistoricalFact(historical);
        record.setBundleDigest(digest);
        record.setBundleJson(toJson(bundle));
        record.setReplayResultJson(body.hasNonNull("replay_result")
                ? toJson(body.get("replay_result")) : null);
        try {
            bundles.insert(record);
        } catch (DuplicateKeyException duplicate) {
            throw new BusinessException(409, "回放包已存在，不得覆盖: " + bundleId);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("contractRecordId", contractRecordId);
        result.put("bundleId", bundleId);
        return result;
    }

    // ---------------------------------------------------------------- 内部工具

    private RecoveryContractRecord requireOwned(Long ownerUserId, Long id) {
        RecoveryContractRecord record = contracts.findByIdForOwner(id, ownerUserId);
        if (record == null) {
            throw new BusinessException(404, "恢复契约不存在: " + id);
        }
        return record;
    }

    private RecoveryContractRecord requireExisting(Long id) {
        Long owner = contracts.findOwnerUserId(id);
        if (owner == null) {
            throw new BusinessException(404, "恢复契约不存在: " + id);
        }
        RecoveryContractRecord record = contracts.findByIdForOwner(id, owner);
        return record;
    }

    private RecoveryObservationRecord toObservation(Long contractRecordId, RecoveryContractRecord contract, JsonNode item) {
        JsonNode payload = item.get("payload");
        JsonNode error = item.get("error");
        if (payload == null && error == null) {
            throw new BusinessException(400, "payload 与 error 至少一个非空");
        }
        RecoveryObservationRecord record = new RecoveryObservationRecord();
        record.setContractRecordId(contractRecordId);
        record.setObservationId(requireText(item, "id"));
        record.setRunId(textOrNull(item, "run_id"));
        record.setVerificationRound(item.hasNonNull("verification_round") ? item.get("verification_round").asInt() : null);
        record.setCollectorId(requireText(item, "collector_id"));
        record.setProbeId(requireText(item, "probe_id"));
        record.setSourceGroup(requireText(item, "source_group"));
        record.setObservedAt(requireText(item, "observed_at"));
        record.setBindingRevision(item.path("binding_revision").asText(contract.getExpectedRevision()));
        record.setObservedRevision(textOrNull(item, "observed_revision"));
        record.setSequence(item.path("sequence").asInt(0));
        record.setElapsedMs(item.hasNonNull("elapsed_ms") ? item.get("elapsed_ms").asInt() : null);
        record.setPayloadJson(payload == null ? null : toJson(payload));
        record.setErrorText(error == null ? null : toJson(error));
        record.setArtifactDigest(textOrNull(item, "artifact_digest"));
        return record;
    }

    private Map<String, Object> summary(RecoveryContractRecord contract, RecoveryReceiptRecord receipt) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("id", contract.getId());
        item.put("contractId", contract.getContractId());
        item.put("contractVersion", contract.getContractVersion());
        item.put("runId", contract.getRunId());
        item.put("scope", contract.getScope());
        item.put("targetId", contract.getTargetId());
        item.put("targetKind", contract.getTargetKind());
        item.put("expectedRevision", contract.getExpectedRevision());
        item.put("digest", contract.getDigest());
        item.put("expiresAfterMs", contract.getExpiresAfterMs());
        item.put("validFrom", contract.getValidFrom());
        item.put("createdAt", contract.getCreatedAt() == null ? null : contract.getCreatedAt().toString());
        item.put("verdict", receipt == null ? null : receipt.getVerdict());
        item.put("receiptState", receipt == null ? null : receipt.getReceiptState());
        item.put("issuedAt", receipt == null ? null : receipt.getIssuedAt());
        item.put("validUntil", receipt == null ? null : receipt.getValidUntil());
        return item;
    }

    private Map<String, Object> createdView(RecoveryContractRecord record, boolean replayed) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", record.getId());
        result.put("contractId", record.getContractId());
        result.put("digest", record.getDigest());
        result.put("idempotentReplay", replayed);
        return result;
    }

    private Map<String, Object> receiptView(RecoveryReceiptRecord record) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("receiptId", record.getReceiptId());
        item.put("runId", record.getRunId());
        item.put("verificationRound", record.getVerificationRound());
        item.put("verdict", record.getVerdict());
        item.put("receiptState", record.getReceiptState());
        item.put("issuedAt", record.getIssuedAt());
        item.put("validUntil", record.getValidUntil());
        item.put("evidenceSnapshotDigest", record.getEvidenceSnapshotDigest());
        item.put("policyVersion", record.getPolicyVersion());
        item.put("receipt", readJson(record.getReceiptJson()));
        item.put("obligationResults", readJson(record.getObligationResultsJson()));
        item.put("probeDecision", readJson(record.getProbeDecisionJson()));
        item.put("invalidationEvents", readJson(record.getInvalidationEventsJson()));
        item.put("createdAt", record.getCreatedAt() == null ? null : record.getCreatedAt().toString());
        return item;
    }

    private Map<String, Object> observationView(RecoveryObservationRecord record) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("observationId", record.getObservationId());
        item.put("runId", record.getRunId());
        item.put("verificationRound", record.getVerificationRound());
        item.put("collectorId", record.getCollectorId());
        item.put("probeId", record.getProbeId());
        item.put("sourceGroup", record.getSourceGroup());
        item.put("observedAt", record.getObservedAt());
        item.put("bindingRevision", record.getBindingRevision());
        item.put("observedRevision", record.getObservedRevision());
        item.put("sequence", record.getSequence());
        item.put("elapsedMs", record.getElapsedMs());
        item.put("payload", readJson(record.getPayloadJson()));
        item.put("error", readJson(record.getErrorText()));
        item.put("artifactDigest", record.getArtifactDigest());
        return item;
    }

    private Map<String, Object> replayView(RecoveryReplayBundleRecord record) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("bundleId", record.getBundleId());
        item.put("parentBundleId", record.getParentBundleId());
        item.put("historicalFact", record.getHistoricalFact());
        item.put("bundleDigest", record.getBundleDigest());
        item.put("bundle", readJson(record.getBundleJson()));
        item.put("replayResult", readJson(record.getReplayResultJson()));
        item.put("createdAt", record.getCreatedAt() == null ? null : record.getCreatedAt().toString());
        return item;
    }

    private String toJson(JsonNode node) {
        try {
            return json.writeValueAsString(node);
        } catch (JsonProcessingException error) {
            throw new BusinessException(400, "JSON 序列化失败: " + error.getOriginalMessage());
        }
    }

    private JsonNode readJson(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return json.readTree(raw);
        } catch (Exception malformed) {
            // 落库内容来自受信写入方；读路径不因单条坏数据整体失败，原文以字符串回显
            return json.getNodeFactory().textNode(raw);
        }
    }

    private static String requireText(JsonNode node, String field) {
        if (node == null || !node.hasNonNull(field) || node.get(field).asText().isBlank()) {
            throw new BusinessException(400, "缺少必填字段: " + field);
        }
        return node.get(field).asText();
    }

    private static String textOrNull(JsonNode node, String field) {
        return node != null && node.hasNonNull(field) ? node.get(field).asText() : null;
    }

    private static long requireLong(JsonNode node, String field) {
        if (node == null || !node.hasNonNull(field)) {
            throw new BusinessException(400, "缺少必填字段: " + field);
        }
        return node.get(field).asLong();
    }
}
