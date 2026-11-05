package com.smartops.cloud;

/**
 * 云资源只读清单契约（OPS-02）。
 *
 * 新厂商接同一契约：分页游标、页大小、凭据由调用方传入，
 * 适配器不自己读配置、不自己持久化，避免第二套资源账。
 */
public interface CloudInventoryProvider {

    CloudProvider provider();

    /**
     * 读取一页实例清单。cursor 为 null 表示第一页。
     *
     * @throws CloudProviderException 权限不足、限流重试耗尽、响应不可解析等
     */
    CloudPage listInstances(CloudAccount account, CloudCredentials credentials, String cursor, int pageSize);
}
