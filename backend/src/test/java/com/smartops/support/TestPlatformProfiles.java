package com.smartops.support;

import com.smartops.security.PlatformAdminGovernance;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;

/**
 * SEC-07 测试夹具：SQL 直接种子出来的管理员没有平台档案。
 * 生产环境由 V20261005 迁移回填，测试里用同一语义显式授予，避免依赖“缺档案=ROOT”的旧漏洞语义。
 */
public final class TestPlatformProfiles {

    private TestPlatformProfiles() {
    }

    /** 按 root 级别授予全部平台能力（等价迁移期首个管理员的回填结果）。 */
    public static void grantRoot(JdbcTemplate jdbc, long userId) {
        grant(jdbc, userId, "root", List.copyOf(PlatformAdminGovernance.ROOT_CAPABILITIES));
    }

    /** 显式建档并授予能力；重复调用以最后一次为准。 */
    public static void grant(JdbcTemplate jdbc, long userId, String level, List<String> capabilities) {
        jdbc.update("DELETE FROM platform_admin_capability WHERE user_id=?", userId);
        jdbc.update("DELETE FROM platform_admin_profile WHERE user_id=?", userId);
        jdbc.update("INSERT INTO platform_admin_profile(user_id,level,appointed_by) VALUES(?,?,NULL)", userId, level);
        for (String capability : capabilities) {
            jdbc.update("INSERT INTO platform_admin_capability(user_id,capability) VALUES(?,?)", userId, capability);
        }
    }
}
