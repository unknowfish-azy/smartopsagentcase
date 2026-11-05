package com.smartops.security;

import java.util.Map;
import java.util.Set;

/** Platform-level administrator hierarchy and capability delegation rules. */
public final class PlatformAdminGovernance {
    public static final String ROOT = "root";
    public static final String DEPUTY = "deputy";
    public static final String SPECIALIST = "specialist";

    public static final Set<String> ROOT_CAPABILITIES = Set.of(
            "admin.users", "admin.config", "admin.audit", "admin.security",
            "teams.view", "teams.manage", "teams.freeze", "teams.audit", "teams.approve");

    /** 能力目录的中文说明在服务端维护：前端只消费，不在页面写死能力清单。 */
    private static final Map<String, String> LABELS = Map.of(
            "admin.users", "账号与平台管理员管理",
            "admin.config", "系统配置（组织、角色、菜单、字典、公告）",
            "admin.audit", "安全审计读取",
            "admin.security", "安全策略与会话处置",
            "teams.view", "团队查看",
            "teams.manage", "团队管理",
            "teams.freeze", "团队冻结",
            "teams.audit", "团队审计",
            "teams.approve", "团队审批");

    private static final Map<String, Set<String>> DELEGABLE = Map.of(
            ROOT, ROOT_CAPABILITIES,
            DEPUTY, Set.of("admin.users", "admin.config", "admin.audit", "teams.view", "teams.manage", "teams.freeze", "teams.audit", "teams.approve"),
            SPECIALIST, Set.of());

    private PlatformAdminGovernance() { }

    public static String label(String capability) {
        return LABELS.getOrDefault(capability, capability);
    }

    public static boolean canGrant(String actorLevel, String capability) {
        return capability != null && DELEGABLE.getOrDefault(actorLevel, Set.of()).contains(capability);
    }

    public static boolean canManage(String actorLevel, String targetLevel) {
        if (ROOT.equals(actorLevel)) return DEPUTY.equals(targetLevel) || SPECIALIST.equals(targetLevel);
        return DEPUTY.equals(actorLevel) && SPECIALIST.equals(targetLevel);
    }
}
