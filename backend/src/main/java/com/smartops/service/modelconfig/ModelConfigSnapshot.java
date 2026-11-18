package com.smartops.service.modelconfig;

import java.util.List;

/**
 * 模型网关配置快照：某个版本生效瞬间的完整路由配置，不含任何密钥。
 *
 * <p>快照分三类数据：模型组（路由模式/额度）、组内路由（优先级/权重）、
 * 连接元数据（模型名/能力标签）。连接密钥永远不进入快照，
 * 由 {@code ModelConnectionService} 在调用时按 id 解密读取。</p>
 */
public record ModelConfigSnapshot(
        int version,
        String capturedAt,
        List<Group> groups,
        List<Connection> connections
) {

    public record Group(
            Long id,
            String slug,
            String name,
            Long ownerUserId,
            String scope,
            boolean enabled,
            String routeMode,
            String defaultCapability,
            Long requestLimit24h,
            Long tokenLimit24h,
            List<Route> routes
    ) {}

    public record Route(
            Long id,
            Long connectionId,
            int priority,
            int weight,
            boolean enabled
    ) {}

    public record Connection(
            Long id,
            Long userId,
            String name,
            String modelName,
            List<String> capabilities,
            boolean enabled
    ) {}
}
