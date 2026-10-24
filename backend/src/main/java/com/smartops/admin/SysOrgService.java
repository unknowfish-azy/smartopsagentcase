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
 * 组织架构：部门（树）与岗位。
 *
 * <p>部门用 parent_id 自引用成树；岗位是扁平字典，可被多个部门复用。
 * 删除部门受保护：有子部门或有用户时返回 409，避免静默破坏组织树。</p>
 */
@Service
public class SysOrgService {

    private final JdbcTemplate jdbc;
    private final SecurityAuditService audit;

    public SysOrgService(JdbcTemplate jdbc, SecurityAuditService audit) {
        this.jdbc = jdbc;
        this.audit = audit;
    }

    /* ── 部门 ─────────────────────────────────────────────────────────── */

    public List<Map<String, Object>> deptTree() {
        List<Map<String, Object>> nodes = jdbc.queryForList("""
                SELECT id,parent_id,name,sort,leader,phone,status,created_at
                  FROM sys_dept ORDER BY parent_id, sort, id
                """);
        Map<Long, Map<String, Object>> byId = new LinkedHashMap<>();
        for (Map<String, Object> node : nodes) {
            node.put("children", new ArrayList<Map<String, Object>>());
            node.put("hasChildren", false);
            byId.put(((Number) node.get("id")).longValue(), node);
        }
        List<Map<String, Object>> roots = new ArrayList<>();
        for (Map<String, Object> node : nodes) {
            long parentId = ((Number) node.get("parent_id")).longValue();
            Map<String, Object> parent = byId.get(parentId);
            if (parentId == 0 || parent == null) {
                roots.add(node);
            } else {
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> children = (List<Map<String, Object>>) parent.get("children");
                children.add(node);
                parent.put("hasChildren", true);
            }
        }
        return roots;
    }

    @Transactional
    public Map<String, Object> createDept(SessionUser actor, long parentId, String name, int sort,
                                          String leader, String phone) {
        String safeName = requireName(name, 64, "部门名称");
        if (parentId != 0) requireExists("sys_dept", parentId, "父部门");
        KeyHolder keys = insert("""
                INSERT INTO sys_dept(parent_id,name,sort,leader,phone) VALUES(?,?,?,?,?)
                """, parentId, safeName, Math.max(0, sort), blankOrNull(leader, 32), blankOrNull(phone, 32));
        audit.record(actor, "DEPT_CREATE", Long.toString(SysKeys.id(keys)), "SUCCESS");
        return deptById(SysKeys.id(keys));
    }

    @Transactional
    public Map<String, Object> updateDept(SessionUser actor, long id, long parentId, String name, int sort,
                                          String leader, String phone) {
        requireExists("sys_dept", id, "部门");
        if (parentId == id) throw new BusinessException(400, "部门不能把父级设为自己");
        if (parentId != 0) {
            requireExists("sys_dept", parentId, "父部门");
            // 若 id 是 parentId 的祖先，把 id 挂到 parentId 下会成环
            if (isAncestor(id, parentId)) throw new BusinessException(400, "父部门不能是该部门的子部门，避免成环");
        }
        jdbc.update("UPDATE sys_dept SET parent_id=?,name=?,sort=?,leader=?,phone=? WHERE id=?",
                parentId, requireName(name, 64, "部门名称"), Math.max(0, sort), blankOrNull(leader, 32), blankOrNull(phone, 32), id);
        audit.record(actor, "DEPT_UPDATE", Long.toString(id), "SUCCESS");
        return deptById(id);
    }

    @Transactional
    public void deleteDept(SessionUser actor, long id) {
        requireExists("sys_dept", id, "部门");
        Integer children = jdbc.queryForObject("SELECT COUNT(*) FROM sys_dept WHERE parent_id=?", Integer.class, id);
        if (children != null && children > 0) throw new BusinessException(409, "该部门下还有子部门，请先移除或转移子部门");
        Integer users = jdbc.queryForObject("SELECT COUNT(*) FROM app_user WHERE dept_id=?", Integer.class, id);
        if (users != null && users > 0) throw new BusinessException(409, "该部门下还有用户，请先把用户转移到其它部门");
        jdbc.update("DELETE FROM sys_dept WHERE id=?", id);
        audit.record(actor, "DEPT_DELETE", Long.toString(id), "SUCCESS");
    }

    @Transactional
    public void setDeptStatus(SessionUser actor, long id, int status) {
        requireExists("sys_dept", id, "部门");
        jdbc.update("UPDATE sys_dept SET status=? WHERE id=?", normalizeStatus(status), id);
        audit.record(actor, "DEPT_STATUS", Long.toString(id), "SUCCESS");
    }

    private Map<String, Object> deptById(long id) {
        return jdbc.queryForList("SELECT id,parent_id,name,sort,leader,phone,status,created_at FROM sys_dept WHERE id=?", id)
                .stream().findFirst().orElseThrow(() -> new BusinessException(404, "部门不存在"));
    }

    /** 判断 ancestor 是否是 of 的祖先（沿 parent_id 向上回溯）。 */
    private boolean isAncestor(long ancestor, long of) {
        long cursor = of;
        for (int depth = 0; depth < 128; depth++) {
            List<Long> parents = jdbc.query("SELECT parent_id FROM sys_dept WHERE id=?", (r, i) -> r.getLong("parent_id"), cursor);
            if (parents.isEmpty() || parents.get(0) == 0) return false;
            if (parents.get(0) == ancestor) return true;
            cursor = parents.get(0);
        }
        return false;
    }

    /* ── 岗位 ─────────────────────────────────────────────────────────── */

    public List<Map<String, Object>> listPosts() {
        return jdbc.queryForList("SELECT id,code,name,sort,status,remark,created_at FROM sys_post ORDER BY sort,id");
    }

    @Transactional
    public Map<String, Object> createPost(SessionUser actor, String code, String name, int sort, String remark) {
        String safeCode = requireName(code, 64, "岗位编码");
        String safeName = requireName(name, 64, "岗位名称");
        try {
            KeyHolder keys = insert("INSERT INTO sys_post(code,name,sort,remark) VALUES(?,?,?,?)",
                    safeCode, safeName, Math.max(0, sort), blankOrNull(remark, 255));
            audit.record(actor, "POST_CREATE", Long.toString(SysKeys.id(keys)), "SUCCESS");
            return postById(SysKeys.id(keys));
        } catch (org.springframework.dao.DuplicateKeyException duplicate) {
            throw new BusinessException(409, "岗位编码已存在");
        }
    }

    @Transactional
    public Map<String, Object> updatePost(SessionUser actor, long id, String code, String name, int sort, String remark) {
        requireExists("sys_post", id, "岗位");
        try {
            jdbc.update("UPDATE sys_post SET code=?,name=?,sort=?,remark=? WHERE id=?",
                    requireName(code, 64, "岗位编码"), requireName(name, 64, "岗位名称"),
                    Math.max(0, sort), blankOrNull(remark, 255), id);
        } catch (org.springframework.dao.DuplicateKeyException duplicate) {
            throw new BusinessException(409, "岗位编码已存在");
        }
        audit.record(actor, "POST_UPDATE", Long.toString(id), "SUCCESS");
        return postById(id);
    }

    @Transactional
    public void deletePost(SessionUser actor, long id) {
        requireExists("sys_post", id, "岗位");
        Integer users = jdbc.queryForObject("SELECT COUNT(*) FROM app_user WHERE post_id=?", Integer.class, id);
        if (users != null && users > 0) throw new BusinessException(409, "该岗位还有用户，请先调整这些用户的岗位");
        jdbc.update("DELETE FROM sys_post WHERE id=?", id);
        audit.record(actor, "POST_DELETE", Long.toString(id), "SUCCESS");
    }

    @Transactional
    public void setPostStatus(SessionUser actor, long id, int status) {
        requireExists("sys_post", id, "岗位");
        jdbc.update("UPDATE sys_post SET status=? WHERE id=?", normalizeStatus(status), id);
        audit.record(actor, "POST_STATUS", Long.toString(id), "SUCCESS");
    }

    private Map<String, Object> postById(long id) {
        return jdbc.queryForList("SELECT id,code,name,sort,status,remark,created_at FROM sys_post WHERE id=?", id)
                .stream().findFirst().orElseThrow(() -> new BusinessException(404, "岗位不存在"));
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

    private void requireExists(String table, long id, String label) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM " + table + " WHERE id=?", Integer.class, id);
        if (count == null || count == 0) throw new BusinessException(404, label + "不存在");
    }

    private static String requireName(String value, int max, String label) {
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
}
