package com.smartops.operations;

import java.time.Instant;
import java.util.Map;

/**
 * 一次真实采样的结构化结果。所有字段都可能为 null（对应分区解析失败），
 * supported=false 时 reason 说明原因——绝不编造数字。
 */
public record ServerMonitorSample(
        boolean supported,
        String reason,
        Double cpuPercent,
        Long memTotalKb,
        Long memAvailableKb,
        Double load1,
        Double load5,
        Double load15,
        Long diskTotalKb,
        Long diskUsedKb,
        Long diskAvailKb,
        Integer diskUsagePercent,
        Long netRxBytes,
        Long netTxBytes,
        String sampledAt
) {
    public static ServerMonitorSample unsupported(String reason) {
        return new ServerMonitorSample(false, reason, null, null, null, null, null, null,
                null, null, null, null, null, null, null);
    }

    public Map<String, Object> toView() {
        return Map.ofEntries(
                Map.entry("supported", supported),
                Map.entry("reason", reason == null ? "" : reason),
                Map.entry("cpuPercent", cpuPercent),
                Map.entry("memTotalKb", memTotalKb),
                Map.entry("memAvailableKb", memAvailableKb),
                Map.entry("load1", load1),
                Map.entry("load5", load5),
                Map.entry("load15", load15),
                Map.entry("diskTotalKb", diskTotalKb),
                Map.entry("diskUsedKb", diskUsedKb),
                Map.entry("diskAvailKb", diskAvailKb),
                Map.entry("diskUsagePercent", diskUsagePercent),
                Map.entry("netRxBytes", netRxBytes),
                Map.entry("netTxBytes", netTxBytes),
                Map.entry("sampledAt", sampledAt == null ? Instant.now().toString() : sampledAt)
        );
    }
}
