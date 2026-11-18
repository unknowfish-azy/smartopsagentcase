package com.smartops.service.modelconfig;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 控制面策略：快照刷新节奏、发布所需的审批级数与审批人范围。
 *
 * <p>审批级数由部署方决定：0 表示单人可直接发布（默认），
 * 大于 0 时草稿必须先提交审批，且不能由创建人自己审批。</p>
 *
 * <p>{@code approvers} 为空时任意管理员都可审批；配置后只有名单内的
 * 账号（按用户名匹配）可以审批，便于把发布权限收敛到独立审批角色。</p>
 */
@Component
@ConfigurationProperties(prefix = "smartops.model.control-plane")
public class ModelControlPlaneProperties {

    private long refreshMs = 15000;
    private long initialDelayMs = 5000;
    private int requiredApprovals = 0;
    private List<String> approvers = List.of();

    public long getRefreshMs() {
        return refreshMs;
    }

    public void setRefreshMs(long refreshMs) {
        this.refreshMs = refreshMs;
    }

    public long getInitialDelayMs() {
        return initialDelayMs;
    }

    public void setInitialDelayMs(long initialDelayMs) {
        this.initialDelayMs = initialDelayMs;
    }

    public int getRequiredApprovals() {
        return requiredApprovals;
    }

    public void setRequiredApprovals(int requiredApprovals) {
        this.requiredApprovals = Math.max(0, requiredApprovals);
    }

    public List<String> getApprovers() {
        return approvers;
    }

    public void setApprovers(List<String> approvers) {
        this.approvers = approvers == null ? List.of() : approvers.stream()
                .map(String::trim)
                .filter(name -> !name.isEmpty())
                .distinct()
                .toList();
    }
}
