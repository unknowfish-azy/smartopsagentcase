package com.smartops.iac;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * OPS-12：Terraform 计划（{@code terraform show -json}）的脱敏与风险识别。
 *
 * <p>只保留资源地址、类型、模块与动作，不保留 before/after 值：
 * 计划里经常含密码、密钥、证书等敏感字段，落库前必须脱敏。
 * 同时识别 delete / replace，销毁型计划需要显式确认才能审批通过。</p>
 */
public final class TerraformPlanAnalyzer {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final int MAX_CHANGES = 200;

    private TerraformPlanAnalyzer() {}

    public static Analysis analyze(String planJson) {
        if (planJson == null || planJson.isBlank()) {
            throw new BusinessException(400, "IAC_PLAN_EMPTY: 计划内容为空");
        }
        JsonNode root;
        try {
            root = JSON.readTree(planJson);
        } catch (Exception malformed) {
            throw new BusinessException(400, "IAC_PLAN_MALFORMED: 不是合法的 Terraform plan JSON");
        }
        if (root == null || !root.isObject()) {
            throw new BusinessException(400, "IAC_PLAN_MALFORMED: 计划根节点必须是对象");
        }
        String formatVersion = text(root, "format_version");
        if (formatVersion != null && !formatVersion.startsWith("1.")) {
            throw new BusinessException(400, "IAC_PLAN_FORMAT_UNSUPPORTED: " + formatVersion);
        }
        JsonNode changes = root.get("resource_changes");
        if (changes == null || !changes.isArray()) {
            // 没有 resource_changes 不是"无变更"，而是拿错了输出（例如 terraform show 的 state）。
            throw new BusinessException(400, "IAC_PLAN_NOT_TERRAFORM: 缺少 resource_changes");
        }

        int create = 0, update = 0, delete = 0, replace = 0;
        boolean destroy = false;
        List<Change> summary = new ArrayList<>();
        List<String> canonical = new ArrayList<>();
        for (JsonNode item : changes) {
            String address = text(item, "address");
            if (address == null || address.isBlank()) continue;
            JsonNode actions = item.path("change").path("actions");
            List<String> actionList = new ArrayList<>();
            if (actions.isArray()) actions.forEach(action -> actionList.add(action.asText()));
            String action = describe(actionList);
            boolean destructive = actionList.contains("delete");
            switch (action) {
                case "create" -> create++;
                case "update" -> update++;
                case "delete" -> delete++;
                case "replace" -> replace++;
                default -> { }
            }
            if (destructive) destroy = true;
            canonical.add(address + "=" + action);
            if (summary.size() < MAX_CHANGES) {
                summary.add(new Change(address, text(item, "type"), text(item, "name"),
                        text(item, "module_address"), action, destructive));
            }
        }
        canonical.sort(Comparator.naturalOrder());
        JsonNode priorState = root.path("prior_state");
        Long serial = priorState.path("serial").isNumber() ? priorState.path("serial").asLong() : null;
        String lineage = text(priorState, "lineage");

        StringBuilder seed = new StringBuilder();
        seed.append(text(root, "terraform_version")).append('|').append(lineage).append('|').append(serial).append('|');
        canonical.forEach(entry -> seed.append(entry).append(';'));
        String digest = sha256(seed.toString());

        return new Analysis(text(root, "terraform_version"), serial, lineage,
                create, update, delete, replace, create + update + delete + replace,
                destroy, digest, List.copyOf(summary), changes.size() > MAX_CHANGES);
    }

    /** 计划摘要的持久化 JSON：只有元数据，可安全落库与展示。 */
    static String summaryJson(Analysis analysis) {
        try {
            return JSON.writeValueAsString(analysis.changes());
        } catch (Exception failure) {
            throw new IllegalStateException("IAC_PLAN_SUMMARY_WRITE_FAILED", failure);
        }
    }

    private static String describe(List<String> actions) {
        if (actions.contains("delete") && actions.contains("create")) return "replace";
        if (actions.contains("create")) return "create";
        if (actions.contains("update")) return "update";
        if (actions.contains("delete")) return "delete";
        if (actions.contains("read")) return "read";
        return "no-op";
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        return value == null || value.isNull() ? null : value.asText();
    }

    static String sha256(String text) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder(bytes.length * 2);
            for (byte value : bytes) hex.append(String.format("%02x", value));
            return hex.toString();
        } catch (NoSuchAlgorithmException unsupported) {
            throw new IllegalStateException("SHA-256_UNAVAILABLE", unsupported);
        }
    }

    /** 计划分析结果；{@code changes} 已脱敏且截断到 {@value #MAX_CHANGES} 条。 */
    public record Analysis(String terraformVersion, Long stateSerial, String stateLineage,
                           int createCount, int updateCount, int deleteCount, int replaceCount,
                           int changeCount, boolean destroyDetected, String digest,
                           List<Change> changes, boolean truncated) {}

    /** 单个资源变更摘要，不含任何属性值。 */
    public record Change(String address, String type, String name, String moduleAddress,
                         String action, boolean destructive) {}
}
