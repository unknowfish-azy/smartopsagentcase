package com.smartops.support;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 恢复契约草案的公共组装器（P1-4 抽取，工单侧与预测面共用）。
 *
 * <p>草案与 recovery-contract/v1 schema 同形，digest 恒为空串——平台不越权签发：
 * 谓词核对、canonical digest 计算、内部端点登记全部留在 Agent 侧。
 * window/budgets 是 semantics.md 的冻结常量，全平台只在此处定义一份，
 * 签发前不得修改。</p>
 *
 * <p>调用方只负责两件事：给出目标服务标识与模板/证据组语义，
 * 以及决定草案生成后是否留痕（工单侧写时间线，预测面无实体不留痕）。</p>
 */
public final class RecoveryContractDrafts {

    private RecoveryContractDrafts() {
    }

    /** 归一化为契约合法标识：^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$。 */
    public static String toIdent(String raw) {
        String cleaned = (raw == null ? "" : raw).toLowerCase().replaceAll("[^a-z0-9._:-]+", "-");
        cleaned = cleaned.replaceAll("^-+", "").replaceAll("-+$", "");
        if (cleaned.isEmpty()) {
            cleaned = "unknown-service";
        }
        if (!cleaned.matches("^[A-Za-z0-9].*")) {
            cleaned = "svc-" + cleaned;
        }
        return cleaned.length() > 96 ? cleaned.substring(0, 96) : cleaned;
    }

    /** window 冻结常量（semantics.md）：采样分组与间隙约束，签发前不可修改。 */
    public static Map<String, Object> frozenWindow() {
        return Map.of(
                "sample_groups", 3,
                "min_first_last_gap_ms", 4000,
                "max_adjacent_gap_ms", 4000,
                "max_intra_group_skew_ms", 1250,
                "min_next_group_gap_ms", 2000);
    }

    /** budgets 冻结常量（semantics.md）：探测预算与超时/TTL，签发前不可修改。 */
    public static Map<String, Object> frozenBudgets() {
        return Map.of(
                "max_probe_calls", 12,
                "per_probe_timeout_ms", 1000,
                "run_deadline_ms", 30000,
                "evidence_ttl_ms", 15000,
                "receipt_ttl_ms", 8000);
    }

    /**
     * 组装「服务健康观察」义务（service-health-ok 占位谓词，签发前需按团队谓词库核对替换）。
     */
    public static Map<String, Object> serviceHealthObligation(String ident, String service,
                                                              List<String> sourceGroups) {
        Map<String, Object> target = new LinkedHashMap<>();
        target.put("target_id", ident + "-primary");
        target.put("target_kind", "SERVICE");

        Map<String, Object> obligation = new LinkedHashMap<>();
        obligation.put("obligation_id", "service-health-observed");
        obligation.put("predicate_id", "service-health-ok");
        obligation.put("predicate_version", "v1");
        obligation.put("required", true);
        obligation.put("weight", 1);
        obligation.put("collector_ids", List.of("metric-collector"));
        obligation.put("source_groups", sourceGroups);
        obligation.put("binding_revision", "unspecified");
        obligation.put("scope", ident);
        obligation.put("target", target);
        obligation.put("predicate_params", Map.of("service", service));
        return obligation;
    }

    /**
     * 组装一份完整草案。
     *
     * @param service      目标服务（原文，进 predicate_params）
     * @param idPrefix     草案 id 前缀（如 incident- / forecast-），后接时间戳
     * @param templateId   模板标识（incident-reactive / forecast-preventive）
     * @param sourceGroups 证据组（草案与义务共用同一组）
     */
    public static Map<String, Object> forService(String service, String idPrefix, String templateId,
                                                 List<String> sourceGroups) {
        String ident = toIdent(service);

        Map<String, Object> target = new LinkedHashMap<>();
        target.put("target_id", ident + "-primary");
        target.put("target_kind", "SERVICE");

        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put("schema_version", "recovery-contract/v1");
        draft.put("id", idPrefix + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmss")));
        draft.put("version", "v1");
        draft.put("scope", ident);
        draft.put("target", target);
        draft.put("expected_revision", "unspecified");
        draft.put("template_id", templateId);
        draft.put("template_version", "v1");
        draft.put("obligations", List.of(serviceHealthObligation(ident, service, sourceGroups)));
        draft.put("source_groups", sourceGroups);
        draft.put("window", frozenWindow());
        draft.put("budgets", frozenBudgets());
        draft.put("expires_after", 3600000);
        draft.put("digest", "");
        return draft;
    }
}
