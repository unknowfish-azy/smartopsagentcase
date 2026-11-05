package com.smartops.cloud;

import java.util.Map;

/**
 * 云厂商返回的一条资源快照（只读）。
 *
 * 这里只保留 CMDB 需要的最小字段；厂商私有字段放 providerMetadata，
 * 避免把云 API 响应结构渗进资源身份与关系模型。
 */
public record CloudResourceSnapshot(
        String providerResourceId,
        String resourceType,
        String name,
        String region,
        String providerStatus,
        String publicIp,
        String privateIp,
        String environment,
        String business,
        String owner,
        Map<String, String> tags,
        Map<String, String> providerMetadata
) {
    public CloudResourceSnapshot {
        tags = tags == null ? Map.of() : Map.copyOf(tags);
        providerMetadata = providerMetadata == null ? Map.of() : Map.copyOf(providerMetadata);
    }
}
