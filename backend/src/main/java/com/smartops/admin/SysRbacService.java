package com.smartops.admin;

import com.smartops.exception.BusinessException;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * RBAC：角色与菜单权限。
 *
 * <p>菜单三级模型：目录（导航分组）/ 菜单（页面）/ 按钮（权限点）。
 * 按钮权限标识采用 {@code system:module:action} 三段式，与 KOI-ADMIN 一致。</p>
 *
 * <p>角色授权用"整树替换"而非增量：前端把勾选的菜单 id 一次提交，服务端先清后插，
 * 避免增量导致的幽灵权限（旧勾选没取消掉）。</p>
 */
@Service
public class SysRbacService {

    private final JdbcTemplate jdbc;
    private final SecurityAuditService audit;

    public SysRbacService(JdbcTemplate jdbc, SecurityAuditService audit) {
        this.jdbc = jdbc;
        this.audit = audit;
    }

    /* ── 角色 ─────────────────────────────────────────────────────────── */

    public List<Map<String, Object>> listRoles() {
        List<Map<String, Object>> roles = jdbc.queryForList("""
                SELECT id,name,code,sort,data_scope,status,remark,created_at FROM sys_role ORDER BY sort,id
                """);
        for (Map<String, Object> role : roles) {
            long id = ((Number) role.get("id")).longValue();
            role.put("userCount", jdbc.queryForObject("SELECT COUNT(*) FROM sys_user_role WHERE role_id=?", Long.class, id));
        }
        return roles;
    }

    @Transactional
    public Map<String, Object> createRole(SessionUser actor, String name, String code, int sort,
                                          int dataScope, String remark) {
        try {
            KeyHolder keys = insert("INSERT INTO sys_role(name,code,sort,data_scope,remark) VALUES(?,?,?,?,?)",
                    requireText(name, 64, "角色名称"), requireText(code, 64, "角色编码"),
                    Math.max(0, sort), normalizeDataScope(dataScope), blankOrNull(remark, 255));
            audit.record(actor, "ROLE_CREATE", Long.toString(SysKeys.id(keys)), "SUCCESS");
            return roleById(SysKeys.id(keys));
        } catch (org.springframework.dao.DuplicateKeyException duplicate) {
            throw new BusinessException(409, "角色编码已存在");
        }
    }

    @Transactional
    public Map<String, Object> updateRole(SessionUser actor, long id, String name, String code, int sort,
                                          int dataScope, String remark) {
        requireRole(id);
        try {
            jdbc.update("UPDATE sys_role SET name=?,code=?,sort=?,data_scope=?,remark=? WHERE id=?",
                    requireText(name, 64, "角色名称"), requireText(code, 64, "角色编码"),
                    Math.max(0, sort), normalizeDataScope(dataScope), blankOrNull(remark, 255), id);
        } catch (org.springframework.dao.DuplicateKeyException duplicate) {
            throw new BusinessException(409, "角色编码已存在");
        }
        audit.record(actor, "ROLE_UPDATE", Long.toString(id), "SUCCESS");
        return roleById(id);
    }

    @Transactional
    public void deleteRole(SessionUser actor, long id) {
        requireRole(id);
        Integer users = jdbc.queryForObject("SELECT COUNT(*) FROM sys_user_role WHERE role_id=?", Integer.class, id);
        if (users != null && users > 0) throw new BusinessException(409, "该角色下还有用户，请先移除或转移这些用户的角色");
        jdbc.update("DELETE FROM sys_role WHERE id=?", id);
        audit.record(actor, "ROLE_DELETE", Long.toString(id), "SUCCESS");
    }

    @Transactional
    public void setRoleStatus(SessionUser actor, long id, int status) {
        requireRole(id);
        jdbc.update("UPDATE sys_role SET status=? WHERE id=?", normalizeStatus(status), id);
        audit.record(actor, "ROLE_STATUS", Long.toString(id), "SUCCESS");
    }

    /** 把菜单/按钮权限整树授权给角色。menuIds 可为空（表示清空）。 */
    @Transactional
    public void grantMenus(SessionUser actor, long roleId, List<Long> menuIds) {
        requireRole(roleId);
        List<Long> normalized = menuIds == null ? List.of() : menuIds.stream().distinct().toList();
        for (long menuId : normalized) requireMenu(menuId);
        jdbc.update("DELETE FROM sys_role_menu WHERE role_id=?", roleId);
        for (long menuId : normalized) {
            jdbc.update("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(?,?)", roleId, menuId);
        }
        audit.record(actor, "ROLE_MENU_GRANT", Long.toString(roleId), "SUCCESS");
    }

    /** 角色的菜单 id 集合，供前端回显已勾选节点。 */
    public List<Long> roleMenuIds(long roleId) {
        requireRole(roleId);
        return jdbc.query("SELECT menu_id FROM sys_role_menu WHERE role_id=?", (r, i) -> r.getLong("menu_id"), roleId);
    }

    /* ── 菜单 ─────────────────────────────────────────────────────────── */

    public List<Map<String, Object>> menuTree() {
        List<Map<String, Object>> nodes = jdbc.queryForList("""
                SELECT id,parent_id,name,type,path,component,perms,icon,sort,visible,status,created_at
                  FROM sys_menu ORDER BY parent_id, sort, id
                """);
        Map<Long, Map<String, Object>> byId = new LinkedHashMap<>();
        for (Map<String, Object> node : nodes) {
            node.put("children", new ArrayList<Map<String, Object>>());
            byId.put(((Number) node.get("id")).longValue(), node);
        }
        List<Map<String, Object>> roots = new ArrayList<>();
        for (Map<String, Object> node : nodes) {
            long parentId = ((Number) node.get("parent_id")).longValue();
            Map<String, Object> parent = byId.get(parentId);
            if (parentId == 0 || parent == null) roots.add(node);
            else {
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> children = (List<Map<String, Object>>) parent.get("children");
                children.add(node);
            }
        }
        return roots;
    }

    @Transactional
    public Map<String, Object> createMenu(SessionUser actor, long parentId, String name, int type, String path,
                                          String component, String perms, String icon, int sort, boolean visible) {
        if (parentId != 0) requireMenu(parentId);
        KeyHolder keys = insert("""
                INSERT INTO sys_menu(parent_id,name,type,path,component,perms,icon,sort,visible)
                VALUES(?,?,?,?,?,?,?,?,?)
                """, parentId, requireText(name, 64, "菜单名称"), normalizeType(type),
                blankOrNull(path, 200), blankOrNull(component, 200), blankOrNull(perms, 200),
                blankOrNull(icon, 64), Math.max(0, sort), visible ? 1 : 0);
        audit.record(actor, "MENU_CREATE", Long.toString(SysKeys.id(keys)), "SUCCESS");
        return menuById(SysKeys.id(keys));
    }

    @Transactional
    public Map<String, Object> updateMenu(SessionUser actor, long id, long parentId, String name, int type, String path,
                                          String component, String perms, String icon, int sort, boolean visible) {
        requireMenu(id);
        if (parentId == id) throw new BusinessException(400, "菜单不能把父级设为自己");
        if (parentId != 0) {
            requireMenu(parentId);
            if (isAncestor(id, parentId)) throw new BusinessException(400, "父菜单不能是该菜单的子菜单");
        }
        jdbc.update("""
                UPDATE sys_menu SET parent_id=?,name=?,type=?,path=?,component=?,perms=?,icon=?,sort=?,visible=? WHERE id=?
                """, parentId, requireText(name, 64, "菜单名称"), normalizeType(type),
                blankOrNull(path, 200), blankOrNull(component, 200), blankOrNull(perms, 200),
                blankOrNull(icon, 64), Math.max(0, sort), visible ? 1 : 0, id);
        audit.record(actor, "MENU_UPDATE", Long.toString(id), "SUCCESS");
        return menuById(id);
    }

    @Transactional
    public void deleteMenu(SessionUser actor, long id) {
        requireMenu(id);
        Integer children = jdbc.queryForObject("SELECT COUNT(*) FROM sys_menu WHERE parent_id=?", Integer.class, id);
        if (children != null && children > 0) throw new BusinessException(409, "该菜单下还有子菜单，请先移除子菜单");
        jdbc.update("DELETE FROM sys_menu WHERE id=?", id);
        audit.record(actor, "MENU_DELETE", Long.toString(id), "SUCCESS");
    }

    @Transactional
    public void setMenuStatus(SessionUser actor, long id, int status) {
        requireMenu(id);
        jdbc.update("UPDATE sys_menu SET status=? WHERE id=?", normalizeStatus(status), id);
        audit.record(actor, "MENU_STATUS", Long.toString(id), "SUCCESS");
    }

    /** 某个角色的权限标识（perms）集合，供前端判断按钮是否显示。 */
    public List<String> rolePerms(List<Long> roleIds) {
        if (roleIds == null || roleIds.isEmpty()) return List.of();
        String placeholders = String.join(",", java.util.Collections.nCopies(roleIds.size(), "?"));
        return jdbc.query("""
                SELECT DISTINCT m.perms FROM sys_role_menu rm
                  JOIN sys_menu m ON m.id=rm.menu_id
                 WHERE rm.role_id IN (%s) AND m.perms IS NOT NULL AND m.perms <> ''
                """.formatted(placeholders), (r, i) -> r.getString("perms"), roleIds.toArray());
    }

    /* ── 工具 ─────────────────────────────────────────────────────────── */

    private KeyHolder insert(String sql, Object... args) {
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS);
            for (int i = 0; i < args.length; i++) statement.setObject(i + 1, args[i]);
            return statement;
        }, keys);
        return keys;
    }

    private void requireRole(long id) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM sys_role WHERE id=?", Integer.class, id);
        if (count == null || count == 0) throw new BusinessException(404, "角色不存在");
    }

    private void requireMenu(long id) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM sys_menu WHERE id=?", Integer.class, id);
        if (count == null || count == 0) throw new BusinessException(404, "菜单不存在");
    }

    private Map<String, Object> roleById(long id) {
        return jdbc.queryForList("SELECT id,name,code,sort,data_scope,status,remark,created_at FROM sys_role WHERE id=?", id)
                .stream().findFirst().orElseThrow(() -> new BusinessException(404, "角色不存在"));
    }

    private Map<String, Object> menuById(long id) {
        return jdbc.queryForList("""
                SELECT id,parent_id,name,type,path,component,perms,icon,sort,visible,status,created_at
                  FROM sys_menu WHERE id=?
                """, id).stream().findFirst().orElseThrow(() -> new BusinessException(404, "菜单不存在"));
    }

    private boolean isAncestor(long ancestor, long of) {
        long cursor = of;
        for (int depth = 0; depth < 128; depth++) {
            List<Long> parents = jdbc.query("SELECT parent_id FROM sys_menu WHERE id=?", (r, i) -> r.getLong("parent_id"), cursor);
            if (parents.isEmpty() || parents.get(0) == 0) return false;
            if (parents.get(0) == ancestor) return true;
            cursor = parents.get(0);
        }
        return false;
    }

    private static String requireText(String value, int max, String label) {
        if (value == null || value.isBlank()) throw new BusinessException(400, label + "不能为空");
        String trimmed = value.trim();
        if (trimmed.length() > max) throw new BusinessException(400, label + "不超过 " + max + " 字符");
        return trimmed;
    }

    private static String blankOrNull(String value, int max) {
        if (value == null || value.isBlank()) return null;
        String trimmed = value.trim();
        return trimmed.length() <= max ? trimmed : trimmed.substring(0, max);
    }

    private static int normalizeStatus(int status) {
        if (status != 0 && status != 1) throw new BusinessException(400, "状态需为 0（停用）或 1（启用）");
        return status;
    }

    private static int normalizeType(int type) {
        if (type < 1 || type > 3) throw new BusinessException(400, "菜单类型需为 1（目录）/ 2（菜单）/ 3（按钮）");
        return type;
    }

    private static int normalizeDataScope(int scope) {
        if (scope < 1 || scope > 3) throw new BusinessException(400, "数据权限需为 1（全部）/ 2（本部门）/ 3（本人）");
        return scope;
    }
}
