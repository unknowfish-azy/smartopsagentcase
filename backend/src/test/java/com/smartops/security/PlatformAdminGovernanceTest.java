package com.smartops.security;

import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class PlatformAdminGovernanceTest {
    @Test
    void rootCanGrantOnlyDelegableCapabilities() {
        assertTrue(PlatformAdminGovernance.canGrant("root", "teams.view"));
        assertTrue(PlatformAdminGovernance.canGrant("deputy", "teams.view"));
        assertFalse(PlatformAdminGovernance.canGrant("deputy", "admin.security"));
        assertFalse(PlatformAdminGovernance.canGrant("specialist", "teams.view"));
    }

    @Test
    void capabilitySetsAreImmutableAndKnown() {
        assertEquals(Set.of("admin.users", "admin.config", "admin.audit", "admin.security", "teams.view", "teams.manage", "teams.freeze", "teams.audit", "teams.approve"), PlatformAdminGovernance.ROOT_CAPABILITIES);
        assertThrows(UnsupportedOperationException.class, () -> PlatformAdminGovernance.ROOT_CAPABILITIES.add("other"));
    }
}
