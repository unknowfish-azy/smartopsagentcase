package com.smartops.cloud;

/**
 * 云厂商枚举（OPS-02）。
 *
 * implemented 表示"本仓库是否已有真实的只读清单适配器"，
 * 而不是"是否曾经计划支持"。未实现的厂商在同步时会如实返回 SKIPPED，
 * 不会伪造一个空清单当作同步成功。
 */
public enum CloudProvider {

    ALIYUN("aliyun", "阿里云", true),
    TENCENT("tencent", "腾讯云", false),
    HUAWEI("huawei", "华为云", false);

    private final String wireName;
    private final String displayName;
    private final boolean implemented;

    CloudProvider(String wireName, String displayName, boolean implemented) {
        this.wireName = wireName;
        this.displayName = displayName;
        this.implemented = implemented;
    }

    public String wireName() {
        return wireName;
    }

    public String displayName() {
        return displayName;
    }

    public boolean implemented() {
        return implemented;
    }

    public static CloudProvider fromWireName(String value) {
        if (value == null || value.isBlank()) {
            throw new CloudProviderException("CLOUD_PROVIDER_UNKNOWN", "云厂商不能为空");
        }
        for (CloudProvider provider : values()) {
            if (provider.wireName.equalsIgnoreCase(value.trim())) {
                return provider;
            }
        }
        throw new CloudProviderException("CLOUD_PROVIDER_UNKNOWN", "不支持的云厂商：" + value);
    }
}
