package com.smartops.cloud;

import java.time.LocalDateTime;

/**
 * 云账号绑定（不含任何密钥）。
 *
 * teamId 为空表示个人账号；非空时只有该团队成员可读，
 * 跨团队请求在服务层直接拒绝（OPS-02 验收项）。
 */
public record CloudAccount(
        Long id,
        CloudProvider provider,
        String accountId,
        String displayName,
        String region,
        String endpoint,
        String projectId,
        Long teamId,
        Long ownerUserId,
        String credentialRef,
        String credentialScope,
        boolean enabled,
        LocalDateTime lastSyncAt,
        String lastSyncStatus,
        LocalDateTime createdAt
) {
    public String endpointOrDefault() {
        if (endpoint != null && !endpoint.isBlank()) {
            return endpoint.trim();
        }
        return switch (provider) {
            case ALIYUN -> "https://ecs." + region + ".aliyuncs.com";
            case TENCENT -> "https://cvm.tencentcloudapi.com";
            case HUAWEI -> "https://ecs." + region + ".myhuaweicloud.com";
        };
    }
}
