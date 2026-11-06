package com.smartops.integration;

import com.smartops.exception.BusinessException;
import com.smartops.security.AccountSessionRegistry;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * SEC-07：平台治理 fail-closed 语义。
 *
 * <p>“缺档案=最高管理员”是提权漏洞：任何治理迁移之后新建/提升的管理员都会天然获得全能力。
 * 修复后：缺档案只保留最小只读能力；新建/提升必须显式建档（deputy、无能力）；
 * 首个管理员由 bootstrap 显式授 root；治理数据不可用时拒绝展示而非把全部 admin 当 root。</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:user_governance;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class UserAccountGovernanceIntegrationTest {
    @Autowired UserAccountService accounts;
    @Autowired JdbcTemplate jdbc;
    @Autowired AccountSessionRegistry sessions;

    private static SessionUser admin(long id) {
        return new SessionUser(id, "governance-admin-" + id, "admin", "admin", false, 0);
    }

    @Test
    @Order(1)
    void profileLessAdminKeepsOnlyMinimalReadOnlyCapabilities() {
        jdbc.update("DELETE FROM app_user");
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(11,'no-profile-admin',?,'admin')",
                new BCryptPasswordEncoder().encode("GovernancePassword42!"));

        SessionUser actor = admin(11L);
        // 最小只读保留。
        assertThat(accounts.hasPlatformCapability(actor, "admin.audit")).isTrue();
        assertThat(accounts.hasPlatformCapability(actor, "teams.view")).isTrue();
        assertThat(accounts.hasPlatformCapability(actor, "teams.audit")).isTrue();
        // 写能力与配置能力一律拒绝。
        assertThat(accounts.hasPlatformCapability(actor, "admin.users")).isFalse();
        assertThat(accounts.hasPlatformCapability(actor, "admin.config")).isFalse();
        assertThat(accounts.hasPlatformCapability(actor, "admin.security")).isFalse();
        assertThat(accounts.hasPlatformCapability(actor, "teams.freeze")).isFalse();
        assertThat(accounts.hasPlatformCapability(actor, "teams.manage")).isFalse();
    }

    @Test
    @Order(2)
    void profileLessAdminCannotAppointOrListGovernance() {
        SessionUser actor = admin(11L);
        assertThatThrownBy(() -> accounts.appointPlatformAdmin(actor, 11L, "deputy", List.of("admin.users")))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("平台权限不足");
        assertThatThrownBy(() -> accounts.platformAdministrators(actor))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("平台权限不足");
    }

    @Test
    @Order(3)
    void createdAdminGetsProfileWithoutCapabilities() {
        SessionUser root = admin(11L);
        com.smartops.support.TestPlatformProfiles.grantRoot(jdbc, 11L);

        accounts.create("governance-new-admin", "StrongAdminPassword42!", "admin", null, null, null, root);

        String level = jdbc.queryForObject("SELECT level FROM platform_admin_profile WHERE user_id=(SELECT id FROM app_user WHERE username='governance-new-admin')", String.class);
        assertThat(level).isEqualTo("deputy");
        Long newId = jdbc.queryForObject("SELECT id FROM app_user WHERE username='governance-new-admin'", Long.class);
        Integer capabilities = jdbc.queryForObject("SELECT COUNT(*) FROM platform_admin_capability WHERE user_id=?", Integer.class, newId);
        assertThat(capabilities).isZero();
        // 默认无能力：除最小只读外全部拒绝。
        SessionUser created = new SessionUser(newId, "governance-new-admin", "admin", "admin", false, 0);
        assertThat(accounts.hasPlatformCapability(created, "admin.users")).isFalse();
        assertThat(accounts.hasPlatformCapability(created, "admin.audit")).isTrue();
    }

    @Test
    @Order(4)
    void promotedOperatorGetsProfileWithoutCapabilities() {
        jdbc.update("INSERT INTO app_user(id,username,password_hash,role) VALUES(22,'governance-operator',?,'operator')",
                new BCryptPasswordEncoder().encode("GovernancePassword42!"));
        SessionUser root = admin(11L);

        accounts.update(22L, "admin", true, null, null, null, root);

        String level = jdbc.queryForObject("SELECT level FROM platform_admin_profile WHERE user_id=22", String.class);
        assertThat(level).isEqualTo("deputy");
        Integer capabilities = jdbc.queryForObject("SELECT COUNT(*) FROM platform_admin_capability WHERE user_id=22", Integer.class, 22L);
        assertThat(capabilities).isZero();
    }

    @Test
    @Order(5)
    void bootstrapGrantsRootProfileToFirstAdmin() {
        jdbc.queryForList("SELECT id FROM app_user", Long.class).forEach(sessions::revokeUser);
        jdbc.update("DELETE FROM platform_admin_capability");
        jdbc.update("DELETE FROM platform_admin_profile");
        jdbc.update("DELETE FROM account_security");
        jdbc.update("DELETE FROM app_user");

        accounts.bootstrap("governance-root", "BootstrapRootPassword42!");

        Long rootId = jdbc.queryForObject("SELECT id FROM app_user WHERE username='governance-root'", Long.class);
        assertThat(jdbc.queryForObject("SELECT level FROM platform_admin_profile WHERE user_id=?", String.class, rootId)).isEqualTo("root");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM platform_admin_capability WHERE user_id=?", Integer.class, rootId))
                .isEqualTo(9);
        SessionUser actor = new SessionUser(rootId, "governance-root", "admin", "admin", false, 0);
        assertThat(accounts.hasPlatformCapability(actor, "admin.users")).isTrue();
        assertThat(accounts.hasPlatformCapability(actor, "teams.approve")).isTrue();
    }

    @Test
    @Order(6)
    void governanceListingFailsClosedWhenTablesUnavailable() {
        SessionUser root = admin(11L);
        jdbc.execute("DROP TABLE platform_admin_capability");
        try {
            // 能力判定 fail-closed：治理数据不可用转为明确 500，绝不回退为放行。
            assertThatThrownBy(() -> accounts.hasPlatformCapability(root, "admin.users"))
                    .isInstanceOf(BusinessException.class)
                    .hasMessageContaining("平台治理数据不可用");
            assertThatThrownBy(() -> accounts.platformAdministrators(root))
                    .isInstanceOf(BusinessException.class)
                    .hasMessageContaining("平台治理数据不可用");
        } finally {
            jdbc.execute("CREATE TABLE platform_admin_capability (user_id BIGINT NOT NULL, capability VARCHAR(64) NOT NULL, granted_by BIGINT NULL, granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, capability))");
        }
    }
}
