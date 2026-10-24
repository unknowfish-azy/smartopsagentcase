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
import java.util.List;
import java.util.Map;

/**
 * 数据字典：类型（sys_dict_type）与数据（sys_dict_data）。
 *
 * <p>字典让"状态/类型/类别"这类枚举从代码里解放出来，改配置不改代码 ——
 * 这是企业化系统里最基础也最容易漏的一块。</p>
 */
@Service
public class SysDictService {

    private final JdbcTemplate jdbc;
    private final SecurityAuditService audit;

    public SysDictService(JdbcTemplate jdbc, SecurityAuditService audit) {
        this.jdbc = jdbc;
        this.audit = audit;
    }

    /* ── 字典类型 ─────────────────────────────────────────────────────── */

    public List<Map<String, Object>> listTypes() {
        return jdbc.queryForList("SELECT id,name,type,status,remark,created_at FROM sys_dict_type ORDER BY id");
    }

    @Transactional
    public Map<String, Object> createType(SessionUser actor, String name, String type, String remark) {
        try {
            KeyHolder keys = insert("INSERT INTO sys_dict_type(name,type,remark) VALUES(?,?,?)",
                    requireText(name, 64, "字典名称"), requireText(type, 100, "字典类型"),
                    blankOrNull(remark, 255));
            audit.record(actor, "DICT_TYPE_CREATE", Long.toString(SysKeys.id(keys)), "SUCCESS");
            return typeById(SysKeys.id(keys));
        } catch (org.springframework.dao.DuplicateKeyException duplicate) {
            throw new BusinessException(409, "字典类型已存在");
        }
    }

    @Transactional
    public Map<String, Object> updateType(SessionUser actor, long id, String name, String type, String remark) {
        requireType(id);
        try {
            jdbc.update("UPDATE sys_dict_type SET name=?,type=?,remark=? WHERE id=?",
                    requireText(name, 64, "字典名称"), requireText(type, 100, "字典类型"),
                    blankOrNull(remark, 255), id);
        } catch (org.springframework.dao.DuplicateKeyException duplicate) {
            throw new BusinessException(409, "字典类型已存在");
        }
        audit.record(actor, "DICT_TYPE_UPDATE", Long.toString(id), "SUCCESS");
        return typeById(id);
    }

    @Transactional
    public void deleteType(SessionUser actor, long id) {
        requireType(id);
        jdbc.update("DELETE FROM sys_dict_type WHERE id=?", id);
        audit.record(actor, "DICT_TYPE_DELETE", Long.toString(id), "SUCCESS");
    }

    @Transactional
    public void setTypeStatus(SessionUser actor, long id, int status) {
        requireType(id);
        jdbc.update("UPDATE sys_dict_type SET status=? WHERE id=?", normalizeStatus(status), id);
        audit.record(actor, "DICT_TYPE_STATUS", Long.toString(id), "SUCCESS");
    }

    /* ── 字典数据 ─────────────────────────────────────────────────────── */

    public List<Map<String, Object>> listData(String type) {
        requireText(type, 100, "字典类型");
        return jdbc.queryForList("""
                SELECT id,type,label,dict_value,sort,status,remark,created_at
                  FROM sys_dict_data WHERE type=? ORDER BY sort,id
                """, type);
    }

    /** 给前端下拉用：只返回启用的 label/value 对。 */
    public List<Map<String, Object>> enabledData(String type) {
        return listData(type).stream()
                .filter(row -> Integer.valueOf(1).equals(row.get("status")))
                .toList();
    }

    @Transactional
    public Map<String, Object> createData(SessionUser actor, String type, String label, String value,
                                          int sort, String remark) {
        requireTypeName(type);
        KeyHolder keys = insert("INSERT INTO sys_dict_data(type,label,dict_value,sort,remark) VALUES(?,?,?,?,?)",
                type, requireText(label, 100, "字典标签"), requireText(value, 100, "字典键值"),
                Math.max(0, sort), blankOrNull(remark, 255));
        audit.record(actor, "DICT_DATA_CREATE", Long.toString(SysKeys.id(keys)), "SUCCESS");
        return dataById(SysKeys.id(keys));
    }

    @Transactional
    public Map<String, Object> updateData(SessionUser actor, long id, String type, String label, String value,
                                          int sort, String remark) {
        requireData(id);
        requireTypeName(type);
        jdbc.update("UPDATE sys_dict_data SET type=?,label=?,dict_value=?,sort=?,remark=? WHERE id=?",
                type, requireText(label, 100, "字典标签"), requireText(value, 100, "字典键值"),
                Math.max(0, sort), blankOrNull(remark, 255), id);
        audit.record(actor, "DICT_DATA_UPDATE", Long.toString(id), "SUCCESS");
        return dataById(id);
    }

    @Transactional
    public void deleteData(SessionUser actor, long id) {
        requireData(id);
        jdbc.update("DELETE FROM sys_dict_data WHERE id=?", id);
        audit.record(actor, "DICT_DATA_DELETE", Long.toString(id), "SUCCESS");
    }

    @Transactional
    public void setDataStatus(SessionUser actor, long id, int status) {
        requireData(id);
        jdbc.update("UPDATE sys_dict_data SET status=? WHERE id=?", normalizeStatus(status), id);
        audit.record(actor, "DICT_DATA_STATUS", Long.toString(id), "SUCCESS");
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

    private void requireType(long id) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM sys_dict_type WHERE id=?", Integer.class, id);
        if (count == null || count == 0) throw new BusinessException(404, "字典类型不存在");
    }

    private void requireTypeName(String type) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM sys_dict_type WHERE type=?", Integer.class, type);
        if (count == null || count == 0) throw new BusinessException(404, "字典类型不存在");
    }

    private void requireData(long id) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM sys_dict_data WHERE id=?", Integer.class, id);
        if (count == null || count == 0) throw new BusinessException(404, "字典数据不存在");
    }

    private Map<String, Object> typeById(long id) {
        return jdbc.queryForList("SELECT id,name,type,status,remark,created_at FROM sys_dict_type WHERE id=?", id)
                .stream().findFirst().orElseThrow(() -> new BusinessException(404, "字典类型不存在"));
    }

    private Map<String, Object> dataById(long id) {
        return jdbc.queryForList("SELECT id,type,label,dict_value,sort,status,remark,created_at FROM sys_dict_data WHERE id=?", id)
                .stream().findFirst().orElseThrow(() -> new BusinessException(404, "字典数据不存在"));
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
}
