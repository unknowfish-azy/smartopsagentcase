package com.smartops.radar;

import java.time.Instant;
import java.util.Set;

/**
 * 资源雷达来源。
 *
 * <p>采集器类型、频道与可信等级都走白名单，避免前端传入任意字符串落库。</p>
 */
public record RadarSource(Long id, String name, String collectorType, String url, String channel,
                          String trustLevel, boolean enabled, int intervalMinutes,
                          Instant lastRunAt, Instant nextRunAt, String lastStatus, String lastError,
                          Long createdBy, Instant createdAt, Instant updatedAt) {

    public static final Set<String> COLLECTOR_TYPES = Set.of("RSS", "JSON_API", "GITHUB", "HTTP_PAGE");

    /** 运维资源域，替代“投资赛道”语义。 */
    public static final Set<String> CHANNELS = Set.of(
            "CLOUD", "GPU", "MODEL", "DEVTOOL", "CERT", "PLUGIN", "HARDWARE", "SECURITY");

    /** L0 官方活动页 / L1 官方文档 / L2 社区实测 / L3 聚合转述 / L4 未核实草案。 */
    public static final Set<String> TRUST_LEVELS = Set.of("L0", "L1", "L2", "L3", "L4");
}
