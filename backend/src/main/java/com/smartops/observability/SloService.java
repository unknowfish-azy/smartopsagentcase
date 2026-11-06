package com.smartops.observability;

import com.smartops.exception.BusinessException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * OPS-10：SLI/SLO 与恢复判定。
 *
 * <p>只从平台自有事实表计算，不造数：每个 SLI 都返回分子、分母、窗口与来源表，
 * 口径可复核。HTTP 可用率/错误率/延迟由 Prometheus 规则文件按标准 actuator 指标计算；
 * 本服务负责执行成功率、采集新鲜度、恢复核验率。</p>
 *
 * <p>数据质量必须显式：部署声明的数据来源为 REAL/MOCK/FIXTURE 时原样标注；
 * 样本不足时标 DEGRADED/INSUFFICIENT，绝不把不足样本写成达标。</p>
 */
@Service
public class SloService {

    /** 恢复判定只认独立业务证据（核验回执 + 观测记录 + 运行链路），不读告警"已关闭"作为恢复依据。 */
    private static final String RECOVERED = "RECOVERED";

    private final JdbcTemplate jdbc;
    private final String dataSource;

    public SloService(JdbcTemplate jdbc,
                      @Value("${smartops.observability.data-source:REAL}") String dataSource) {
        this.jdbc = jdbc;
        this.dataSource = normalizeDataSource(dataSource);
    }

    public List<Evaluation> evaluate(int windowHours) {
        if (windowHours < 1 || windowHours > 168) {
            throw new BusinessException(400, "SLO_WINDOW_INVALID: 1..168 小时");
        }
        Instant end = Instant.now();
        Instant start = end.minus(Duration.ofHours(windowHours));

        List<Evaluation> result = new ArrayList<>();
        result.add(executionSuccess(start, windowHours));
        result.add(collectionFreshness(end, windowHours));
        result.add(recoveryVerification(end, start, windowHours));
        return result;
    }

    /**
     * 恢复判定：VERIFIED 回执且 ACTIVE 且未过期才算恢复；仅有告警关闭不算。
     */
    public RecoveryVerdict judgeRecovery(long contractRecordId, Long userId) {
        List<Map<String, Object>> contracts = jdbc.queryForList("""
                SELECT contract_id,target_id,owner_user_id,run_id
                  FROM recovery_contract_record WHERE id=?
                """, contractRecordId);
        if (contracts.isEmpty()) throw new BusinessException(404, "RECOVERY_CONTRACT_NOT_FOUND");
        Map<String, Object> contract = contracts.get(0);
        long ownerUserId = ((Number) contract.get("owner_user_id")).longValue();
        if (userId != null && userId != ownerUserId) {
            throw new BusinessException(404, "RECOVERY_CONTRACT_NOT_FOUND");
        }
        long runId = ((Number) contract.get("run_id")).longValue();
        String contractId = (String) contract.get("contract_id");
        String targetId = (String) contract.get("target_id");

        List<Map<String, Object>> receipts = jdbc.queryForList("""
                SELECT receipt_id,verdict,receipt_state,issued_at,valid_until,evidence_snapshot_digest
                  FROM recovery_receipt_record WHERE contract_record_id=?
                 ORDER BY id DESC LIMIT 1
                """, contractRecordId);
        long observationCount = count(
                "SELECT COUNT(*) FROM recovery_observation_record WHERE contract_record_id=?", contractRecordId);
        String latestObservedAt = jdbc.queryForObject("""
                SELECT MAX(observed_at) FROM recovery_observation_record WHERE contract_record_id=?
                """, String.class, contractRecordId);
        String traceId = jdbc.query("SELECT trace_id FROM operation_run_record WHERE id=?",
                rs -> rs.next() ? rs.getString(1) : null, runId);

        String state;
        String reason;
        String explanation;
        boolean recovered = false;
        String receiptId = null;
        String receiptState = null;
        String verdict = null;
        String issuedAt = null;
        String validUntil = null;
        String evidenceDigest = null;
        if (receipts.isEmpty()) {
            state = "UNKNOWN";
            reason = "NO_RECEIPT";
            explanation = "尚无核验回执，不能判定恢复；告警关闭不等于业务已恢复";
        } else {
            Map<String, Object> receipt = receipts.get(0);
            receiptId = (String) receipt.get("receipt_id");
            receiptState = (String) receipt.get("receipt_state");
            verdict = (String) receipt.get("verdict");
            issuedAt = (String) receipt.get("issued_at");
            validUntil = (String) receipt.get("valid_until");
            evidenceDigest = (String) receipt.get("evidence_snapshot_digest");
            if (!"VERIFIED".equals(verdict)) {
                // 非 VERIFIED 回执按契约必须 NOT_ISSUED，语义是"未通过"，不是"曾通过后失效"。
                state = "NOT_RECOVERED";
                reason = "VERDICT_" + verdict;
                explanation = "最新核验结论为 " + verdict + "，业务证据不足";
            } else if (!"ACTIVE".equals(receiptState)) {
                state = "INVALIDATED";
                reason = "RECEIPT_" + receiptState;
                explanation = "回执已失效（" + receiptState + "），不能作为恢复证据";
            } else if (validUntil == null || validUntil.isBlank()) {
                state = "NOT_RECOVERED";
                reason = "RECEIPT_NOT_TIME_BOUND";
                explanation = "VERIFIED 回执缺少有效期，按不可采信处理";
            } else if (!parseInstant(validUntil).isAfter(Instant.now())) {
                state = "STALE";
                reason = "RECEIPT_EXPIRED";
                explanation = "核验回执已过期，不能按历史结论宣称恢复";
            } else {
                state = RECOVERED;
                reason = "VERIFIED_ACTIVE_RECEIPT";
                explanation = "存在有效的 VERIFIED 回执（" + receiptId + "），且有 "
                        + observationCount + " 条观测证据";
                recovered = true;
            }
        }
        return new RecoveryVerdict(contractRecordId, contractId, targetId, state, recovered, reason, explanation,
                receiptId, receiptState, verdict, issuedAt, validUntil, evidenceDigest, runId, traceId,
                observationCount, latestObservedAt, dataSource);
    }

    // ------------------------------------------------------------------ SLI

    private Evaluation executionSuccess(Instant start, int windowHours) {
        long denominator = count("""
                SELECT COUNT(*) FROM operation_run_record
                 WHERE ended_at IS NOT NULL AND ended_at >= ?
                """, Timestamp.from(start));
        long numerator = count("""
                SELECT COUNT(*) FROM operation_run_record
                 WHERE ended_at IS NOT NULL AND ended_at >= ? AND status='SUCCEEDED'
                """, Timestamp.from(start));
        Definition definition = new Definition("execution_success", "执行成功率",
                "窗口内已结束运行中 status=SUCCEEDED 的占比；分母排除仍在运行（ended_at 为空）的记录",
                "(status='SUCCEEDED' 的运行数) / (已结束运行数)", "operation_run_record", windowHours, 0.99, 20);
        return build(definition, numerator, denominator, List.of("operation_run_record.status"));
    }

    private Evaluation collectionFreshness(Instant end, int windowHours) {
        List<Map<String, Object>> tasks = jdbc.queryForList(
                "SELECT id,interval_sec,last_seen_at FROM sentinel_task WHERE enabled=1");
        long denominator = tasks.size();
        long numerator = 0;
        for (Map<String, Object> task : tasks) {
            Object lastSeen = task.get("last_seen_at");
            if (lastSeen == null) continue;
            int intervalSec = ((Number) task.get("interval_sec")).intValue();
            long allowedSec = Math.max(60L, intervalSec * 2L);
            Instant last = ((Timestamp) lastSeen).toInstant();
            if (!last.isBefore(end.minusSeconds(allowedSec))) numerator++;
        }
        Definition definition = new Definition("collection_freshness", "采集新鲜度",
                "启用任务中 last_seen_at 未超过 max(2×interval, 60s) 的占比；从未采集按不新鲜计",
                "(新鲜任务数) / (启用任务数)", "sentinel_task.last_seen_at", windowHours, 0.95, 5);
        return build(definition, numerator, denominator, List.of("sentinel_task.last_seen_at", "sentinel_task.interval_sec"));
    }

    private Evaluation recoveryVerification(Instant now, Instant start, int windowHours) {
        List<Map<String, Object>> receipts = jdbc.queryForList("""
                SELECT verdict,receipt_state,valid_until FROM recovery_receipt_record WHERE created_at >= ?
                """, Timestamp.from(start));
        long denominator = receipts.size();
        long numerator = 0;
        for (Map<String, Object> receipt : receipts) {
            if (!"VERIFIED".equals(receipt.get("verdict"))) continue;
            if (!"ACTIVE".equals(receipt.get("receipt_state"))) continue;
            String validUntil = (String) receipt.get("valid_until");
            if (validUntil == null || validUntil.isBlank()) continue;
            if (parseInstant(validUntil).isAfter(now)) numerator++;
        }
        Definition definition = new Definition("recovery_verification", "恢复核验率",
                "窗口内核验回执中 VERIFIED+ACTIVE 且未过期的占比；非 VERIFIED 回执按未恢复计",
                "(有效 VERIFIED 回执数) / (核验回执数)", "recovery_receipt_record", windowHours, 0.95, 5);
        return build(definition, numerator, denominator,
                List.of("recovery_receipt_record.verdict", "recovery_receipt_record.receipt_state",
                        "recovery_receipt_record.valid_until"));
    }

    private Evaluation build(Definition def, long numerator, long denominator, List<String> refs) {
        Double value = denominator == 0 ? null : round(numerator / (double) denominator, 4);
        Double burnRate = null;
        Double remainingRatio = null;
        String status;
        if (denominator == 0) {
            status = "NO_DATA";
        } else {
            double budget = 1 - def.objective();
            double actualError = (denominator - numerator) / (double) denominator;
            double remaining = budget - actualError;
            burnRate = round(actualError / budget, 3);
            remainingRatio = round(remaining / budget, 3);
            if (actualError > budget) status = "EXHAUSTED";
            else if (remaining <= budget * 0.2) status = "WARNING";
            else status = "OK";
        }
        String quality = denominator == 0 ? "INSUFFICIENT"
                : (denominator < def.minSamples() ? "DEGRADED" : "REAL");
        return new Evaluation(def.id(), def.title(), def.description(), def.formula(), def.sourceTable(),
                def.windowHours(), def.objective(), numerator, denominator, value, burnRate, remainingRatio,
                status, quality, dataSource, refs);
    }

    private long count(String sql, Object... args) {
        Long value = jdbc.queryForObject(sql, Long.class, args);
        return value == null ? 0 : value;
    }

    private static Instant parseInstant(String text) {
        try {
            return Instant.parse(text);
        } catch (DateTimeParseException ignored) {
            return OffsetDateTime.parse(text).toInstant();
        }
    }

    private static String normalizeDataSource(String raw) {
        String value = raw == null ? "" : raw.trim().toUpperCase(Locale.ROOT);
        return switch (value) {
            case "REAL", "MOCK", "FIXTURE" -> value;
            default -> "UNKNOWN";
        };
    }

    private static double round(double value, int scale) {
        double factor = Math.pow(10, scale);
        return Math.round(value * factor) / factor;
    }

    public record Definition(String id, String title, String description, String formula, String sourceTable,
                             int windowHours, double objective, int minSamples) {}

    public record Evaluation(String id, String title, String description, String formula, String sourceTable,
                             int windowHours, double objective, long numerator, long denominator, Double value,
                             Double burnRate, Double budgetRemainingRatio, String status, String dataQuality,
                             String dataSource, List<String> evidenceRefs) {}

    public record RecoveryVerdict(long contractRecordId, String contractId, String targetId, String state,
                                  boolean recovered, String reason, String explanation, String receiptId,
                                  String receiptState, String verdict, String issuedAt, String validUntil,
                                  String evidenceDigest, long runId, String traceId, long observationCount,
                                  String latestObservedAt, String dataSource) {}
}
