package com.smartops.runbook;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Runbook 的纯函数工具：JSON 读写、内容哈希、输出截断、级别排序。
 *
 * <p>内容哈希是"批准的参数/目标/版本 = 实际执行内容"的校验依据：
 * 计划时按版本 id、参数、目标快照、步骤正文生成，执行前重新计算，
 * 不一致直接拒绝，而不是让执行悄悄偏离审批内容。</p>
 */
final class RunbookSupport {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final int MAX_EXCERPT = 2000;

    private RunbookSupport() {}

    static String toJson(Object value) {
        try {
            return JSON.writeValueAsString(value);
        } catch (Exception failure) {
            throw new IllegalStateException("RUNBOOK_JSON_WRITE_FAILED", failure);
        }
    }

    static Map<String, String> readStringMap(String json) {
        if (json == null || json.isBlank()) return new LinkedHashMap<>();
        try {
            Map<String, String> parsed = JSON.readValue(json, new TypeReference<LinkedHashMap<String, String>>() {});
            return parsed == null ? new LinkedHashMap<>() : parsed;
        } catch (Exception malformed) {
            throw new IllegalStateException("RUNBOOK_JSON_MALFORMED", malformed);
        }
    }

    static List<String> readStringList(String json) {
        if (json == null || json.isBlank()) return new ArrayList<>();
        try {
            List<String> parsed = JSON.readValue(json, new TypeReference<ArrayList<String>>() {});
            return parsed == null ? new ArrayList<>() : parsed;
        } catch (Exception malformed) {
            throw new IllegalStateException("RUNBOOK_JSON_MALFORMED", malformed);
        }
    }

    static <T> List<T> readList(String json, TypeReference<List<T>> type) {
        if (json == null || json.isBlank()) return new ArrayList<>();
        try {
            List<T> parsed = JSON.readValue(json, type);
            return parsed == null ? new ArrayList<>() : parsed;
        } catch (Exception malformed) {
            throw new IllegalStateException("RUNBOOK_JSON_MALFORMED", malformed);
        }
    }

    /**
     * 内容哈希：版本 + 参数 + 目标 + 步骤正文。
     *
     * <p>参数与目标先排序，保证同一份审批内容得到同一个哈希；
     * 步骤按阶段与序号排列，避免因查询顺序不同产生"伪漂移"。</p>
     */
    static String contentHash(long versionId, int version, Map<String, String> parameters,
                              List<String> targets, List<String> canonicalSteps) {
        StringBuilder text = new StringBuilder();
        text.append(versionId).append('|').append(version).append('|');
        parameters.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> text.append(entry.getKey()).append('=').append(entry.getValue()).append(';'));
        text.append('|');
        targets.stream().sorted().forEach(target -> text.append(target).append(';'));
        text.append('|');
        canonicalSteps.forEach(step -> text.append(step).append('\n'));
        return sha256(text.toString());
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

    static String nonce() {
        byte[] bytes = new byte[24];
        new java.security.SecureRandom().nextBytes(bytes);
        return java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    /** 输出摘录：只保留前 N 字符，并明确标注已截断。 */
    static String excerpt(String value) {
        if (value == null) return "";
        String text = value.strip();
        return text.length() <= MAX_EXCERPT ? text : text.substring(0, MAX_EXCERPT) + "\n…（输出已截断）";
    }

    static String truncate(String value, int max) {
        if (value == null) return null;
        String text = value.strip();
        return text.length() <= max ? text : text.substring(0, max);
    }

    static boolean hasText(String value) { return value != null && !value.isBlank(); }

    /** 告警级别排序：数字越小越严重，用于"最低级别"阈值判断。 */
    static int severityRank(String severity) {
        if (severity == null) return 9;
        return switch (severity.trim().toUpperCase(java.util.Locale.ROOT)) {
            case "P0" -> 0;
            case "P1" -> 1;
            case "P2" -> 2;
            case "P3" -> 3;
            default -> 9;
        };
    }
}
