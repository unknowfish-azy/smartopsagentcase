package com.smartops.security;

import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

/**
 * 门户注册中心纯单元测试：锁住「入口层面」的单一事实来源，
 * 新增/修改门户规约时这些不变量必须继续成立。
 */
class PortalCatalogTest {

    private final PortalCatalog portals = new PortalCatalog();

    @Test
    void registersExactlySixParallelPortals() {
        assertEquals(Set.of("user", "admin", "enterprise", "audit", "command", "open"), portals.allowed());
        for (String id : portals.allowed()) assertTrue(portals.isAllowed(id));
        assertFalse(portals.isAllowed(null));
        assertFalse(portals.isAllowed("root"));
        assertFalse(portals.isAllowed(""));
    }

    @Test
    void mapsEachPortalToItsOwnRoleAndAuthority() {
        assertEquals("operator", portals.roleOf("user"));
        assertEquals("ROLE_OPERATOR", portals.authorityOf("user"));
        assertEquals("admin", portals.roleOf("admin"));
        assertEquals("ROLE_ADMIN", portals.authorityOf("admin"));
        assertEquals("enterprise", portals.roleOf("enterprise"));
        assertEquals("ROLE_ENTERPRISE", portals.authorityOf("enterprise"));
        assertEquals("auditor", portals.roleOf("audit"));
        assertEquals("ROLE_AUDIT", portals.authorityOf("audit"));
        assertEquals("commander", portals.roleOf("command"));
        assertEquals("ROLE_COMMAND", portals.authorityOf("command"));
        assertEquals("partner", portals.roleOf("open"));
        assertEquals("ROLE_OPEN", portals.authorityOf("open"));
        // 未知门户 fail-closed
        assertNull(portals.roleOf("ghost"));
        assertNull(portals.authorityOf("ghost"));
    }

    @Test
    void idleTimeoutsFollowTheRegistry() {
        assertEquals(1800, portals.idleSecondsOf("user"));
        assertEquals(600, portals.idleSecondsOf("admin"));
        assertEquals(900, portals.idleSecondsOf("enterprise"));
        assertEquals(600, portals.idleSecondsOf("audit"));
        assertEquals(600, portals.idleSecondsOf("command"));
        assertEquals(1800, portals.idleSecondsOf("open"));
        // 与历史行为一致：未知门户回落 1800
        assertEquals(1800, portals.idleSecondsOf("ghost"));
    }

    @Test
    void onlyUserPortalIsPublicAndSensitiveSetIsAdminAuditCommand() {
        assertTrue(portals.isPublic("user"));
        for (String id : portals.allowed()) {
            if (!"user".equals(id)) assertFalse(portals.isPublic(id), id + " must not be public");
        }
        assertTrue(portals.isSensitive("admin"));
        assertTrue(portals.isSensitive("audit"));
        assertTrue(portals.isSensitive("command"));
        assertFalse(portals.isSensitive("user"));
        assertFalse(portals.isSensitive("enterprise"));
        assertFalse(portals.isSensitive("open"));
        assertFalse(portals.isSensitive("ghost"));
    }

    @Test
    void roleValidationAcceptsOnlyRegisteredRoles() {
        for (String role : new String[]{"operator", "admin", "enterprise", "auditor", "commander", "partner"}) {
            assertTrue(portals.isValidRole(role), role + " should be valid");
        }
        assertFalse(portals.isValidRole(null));
        assertFalse(portals.isValidRole("superuser"));
        assertFalse(portals.isValidRole(""));
    }

    @Test
    void sensitiveRolesAreAdminAuditorAndCommander() {
        assertTrue(portals.isSensitiveRole("admin"));
        assertTrue(portals.isSensitiveRole("auditor"));
        assertTrue(portals.isSensitiveRole("commander"));
        assertFalse(portals.isSensitiveRole("operator"));
        assertFalse(portals.isSensitiveRole("enterprise"));
        assertFalse(portals.isSensitiveRole("partner"));
        assertFalse(portals.isSensitiveRole(null));
    }

    @Test
    void rateLimitsAreStricterForSensitivePortals() {
        assertEquals(new PortalCatalog.RateLimit(5, 900), portals.rateLimitForPortal("admin"));
        assertEquals(new PortalCatalog.RateLimit(5, 900), portals.rateLimitForPortal("audit"));
        assertEquals(new PortalCatalog.RateLimit(5, 900), portals.rateLimitForPortal("command"));
        assertEquals(new PortalCatalog.RateLimit(10, 300), portals.rateLimitForPortal("user"));
        assertEquals(new PortalCatalog.RateLimit(10, 300), portals.rateLimitForPortal("enterprise"));
        assertEquals(new PortalCatalog.RateLimit(10, 300), portals.rateLimitForPortal("open"));

        assertEquals(new PortalCatalog.RateLimit(5, 900), portals.rateLimitForAccount(true));
        assertEquals(new PortalCatalog.RateLimit(10, 300), portals.rateLimitForAccount(false));
    }
}
