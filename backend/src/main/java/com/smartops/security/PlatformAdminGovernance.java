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

    private static final Map<String, Set<String>> DELEGABLE = Map.of(
            ROOT, ROOT_CAPABILITIES,
            DEPUTY, Set.of("admin.users", "admin.config", "admin.audit", "teams.view", "teams.manage", "teams.freeze", "teams.audit", "teams.approve"),
            SPECIALIST, Set.of());

    private PlatformAdminGovernance() { }

    public static boolean canGrant(String actorLevel, String capability) {
        return capability != null && DELEGABLE.getOrDefault(actorLevel, Set.of()).contains(capability);
    }

    public static boolean canManage(String actorLevel, String targetLevel) {
        if (ROOT.equals(actorLevel)) return DEPUTY.equals(targetLevel) || SPECIALIST.equals(targetLevel);
        return DEPUTY.equals(actorLevel) && SPECIALIST.equals(targetLevel);
    }
}
