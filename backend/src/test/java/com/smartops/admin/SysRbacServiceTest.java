package com.smartops.admin;

import com.smartops.exception.BusinessException;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.core.io.ClassPathResource;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * 企业级系统管理的核心行为：部门树成环防护、删除守卫、角色授权整树替换、菜单成环防护。
 */
class SysRbacServiceTest {

    private JdbcTemplate jdbc;
    private SecurityAuditService audit;
    private SysOrgService org;
    private SysRbacService rbac;
    private SysDictService dict;
    private final SessionUser admin = new SessionUser(1L, "admin", "admin");

    @BeforeEach
    void setUp() {
        jdbc = new JdbcTemplate(new DriverManagerDataSource(
                "jdbc:h2:mem:sys-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE", "sa", ""));
        jdbc.execute("CREATE TABLE app_user (id BIGINT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(64), password_hash VARCHAR(100), role VARCHAR(16), enabled BOOLEAN, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        jdbc.execute("CREATE TABLE security_audit_event (id BIGINT AUTO_INCREMENT PRIMARY KEY, actor_id BIGINT, actor_username VARCHAR(64), action VARCHAR(40), target_id VARCHAR(64), outcome VARCHAR(16), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        new ResourceDatabasePopulator(
                new ClassPathResource("db/migration/V20261018__sys_management.sql"),
                new ClassPathResource("db/migration/V20261019__sys_extend_accounts.sql")).execute(jdbc.getDataSource());
        jdbc.update("INSERT INTO app_user(username,password_hash,role,enabled) VALUES('admin','x','admin',TRUE),('u2','x','operator',TRUE)");
        audit = new SecurityAuditService(jdbc);
        org = new SysOrgService(jdbc, audit);
        rbac = new SysRbacService(jdbc, audit);
        dict = new SysDictService(jdbc, audit);
    }

    @Test
    @DisplayName("部门树正确挂接子节点，并禁止把父级设为自己或后代")
    void deptTreeAndCycleGuard() {
        var root = org.createDept(admin, 0, "总部", 0, null, null);
        var child = org.createDept(admin, ((Number) root.get("id")).longValue(), "研发部", 1, "张工", null);
        var tree = org.deptTree();
        assertEquals(1, tree.size());
        assertEquals(1, ((List<?>) tree.get(0).get("children")).size());

        long rootId = ((Number) root.get("id")).longValue();
        long childId = ((Number) child.get("id")).longValue();
        // 父级设为自己
        assertThrows(BusinessException.class, () -> org.updateDept(admin, rootId, rootId, "总部", 0, null, null));
        // 父级设为后代（成环）
        assertThrows(BusinessException.class, () -> org.updateDept(admin, rootId, childId, "总部", 0, null, null));
    }

    @Test
    @DisplayName("有子部门或有用户时删除部门被拒")
    void deptDeleteGuard() {
        var root = org.createDept(admin, 0, "总部", 0, null, null);
        long rootId = ((Number) root.get("id")).longValue();
        var child = org.createDept(admin, rootId, "研发部", 1, null, null);
        // 有子部门
        assertThrows(BusinessException.class, () -> org.deleteDept(admin, rootId));
        // 有用户
        long childId = ((Number) child.get("id")).longValue();
        jdbc.update("UPDATE app_user SET dept_id=? WHERE username='u2'", childId);
        assertThrows(BusinessException.class, () -> org.deleteDept(admin, childId));
        // 清空用户后可删
        jdbc.update("UPDATE app_user SET dept_id=NULL WHERE username='u2'");
        assertDoesNotThrow(() -> org.deleteDept(admin, childId));
    }

    @Test
    @DisplayName("岗位编码唯一，删除有用户的岗位被拒")
    void postGuard() {
        org.createPost(admin, "ENGINEER", "工程师", 1, null);
        assertThrows(BusinessException.class, () -> org.createPost(admin, "ENGINEER", "重复", 1, null));
        var post = org.listPosts().get(0);
        long postId = ((Number) post.get("id")).longValue();
        jdbc.update("UPDATE app_user SET post_id=? WHERE username='u2'", postId);
        assertThrows(BusinessException.class, () -> org.deletePost(admin, postId));
    }

    @Test
    @DisplayName("角色授权采用整树替换，清空后无残留权限")
    void roleGrantReplacesWholeTree() {
        var role = rbac.createRole(admin, "运维", "OPS", 0, 1, null);
        long roleId = ((Number) role.get("id")).longValue();
        var m1 = rbac.createMenu(admin, 0, "系统管理", 1, "/system", "", "", "", 0, true);
        var m2 = rbac.createMenu(admin, 0, "用户管理", 2, "/system/user", "system/user", "system:user:list", "", 1, true);
        long m1Id = ((Number) m1.get("id")).longValue();
        long m2Id = ((Number) m2.get("id")).longValue();

        rbac.grantMenus(admin, roleId, List.of(m1Id, m2Id));
        assertEquals(2, rbac.roleMenuIds(roleId).size());
        // 整树替换：只保留 m2
        rbac.grantMenus(admin, roleId, List.of(m2Id));
        assertEquals(List.of(m2Id), rbac.roleMenuIds(roleId));
        // 清空
        rbac.grantMenus(admin, roleId, List.of());
        assertTrue(rbac.roleMenuIds(roleId).isEmpty());
        // 按钮权限标识能取到
        rbac.grantMenus(admin, roleId, List.of(m2Id));
        assertEquals(List.of("system:user:list"), rbac.rolePerms(List.of(roleId)));
    }

    @Test
    @DisplayName("菜单禁止把父级设为自己或后代，删除有子菜单的被拒")
    void menuCycleAndDeleteGuard() {
        var dir = rbac.createMenu(admin, 0, "目录", 1, "/sys", "", "", "", 0, true);
        long dirId = ((Number) dir.get("id")).longValue();
        var page = rbac.createMenu(admin, dirId, "页面", 2, "/sys/page", "sys/page", "sys:page:list", "", 1, true);
        long pageId = ((Number) page.get("id")).longValue();

        assertThrows(BusinessException.class, () -> rbac.updateMenu(admin, dirId, dirId, "目录", 1, "/sys", "", "", "", 0, true));
        assertThrows(BusinessException.class, () -> rbac.updateMenu(admin, dirId, pageId, "目录", 1, "/sys", "", "", "", 0, true));
        assertThrows(BusinessException.class, () -> rbac.deleteMenu(admin, dirId));
        assertDoesNotThrow(() -> rbac.deleteMenu(admin, pageId));
    }

    @Test
    @DisplayName("字典数据级联删除，类型唯一")
    void dictCascadeAndUnique() {
        dict.createType(admin, "性别", "sys_gender", null);
        assertThrows(BusinessException.class, () -> dict.createType(admin, "重复", "sys_gender", null));
        dict.createData(admin, "sys_gender", "男", "M", 0, null);
        dict.createData(admin, "sys_gender", "女", "F", 1, null);
        assertEquals(2, dict.listData("sys_gender").size());
        assertEquals(2, dict.enabledData("sys_gender").size());
        // 停用一条后 enabledData 只剩一条
        long firstId = ((Number) dict.listData("sys_gender").get(0).get("id")).longValue();
        dict.setDataStatus(admin, firstId, 0);
        assertEquals(1, dict.enabledData("sys_gender").size());
    }
}
