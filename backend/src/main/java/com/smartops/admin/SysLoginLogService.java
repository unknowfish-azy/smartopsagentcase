package com.smartops.admin;

import com.smartops.exception.BusinessException;
import com.smartops.security.SecurityAuditService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 登录日志：记录成功/失败及来源 IP。
 *
 * <p>与操作日志（复用 security_audit_event）分开：登录日志面向"谁在何时从哪里登录/失败"，
 * 是安全审计与异常登录排查的第一现场。</p>
 */
@Service
public class SysLoginLogService {

    private final JdbcTemplate jdbc;

    public SysLoginLogService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void recordSuccess(Long userId, String username, String ip) {
        insert(userId, username, ip, 1, "登录成功");
    }

    public void recordFailure(String username, String ip, String message) {
        insert(null, username, ip, 0, message == null ? "登录失败" : message);
    }

    private void insert(Long userId, String username, String ip, int status, String message) {
        String safeName = username == null ? "unknown" : username.replaceAll("[\\r\\n\\t]", " ").trim();
        jdbc.update("INSERT INTO sys_login_log(user_id,username,ip,status,message) VALUES(?,?,?,?,?)",
                userId, safeName.substring(0, Math.min(64, safeName.length())),
                blankOrNull(ip, 64), status, blankOrNull(message, 255));
    }

    public Map<String, Object> list(String q, int page, int pageSize) {
        SecurityAuditService.validatePage(page, pageSize);
        StringBuilder where = new StringBuilder(" WHERE 1=1");
        List<Object> values = new ArrayList<>();
        if (q != null && !q.isBlank()) {
            if (q.length() > 64) throw new BusinessException(400, "搜索内容不能超过 64 个字符");
            where.append(" AND LOCATE(LOWER(?),LOWER(username))>0");
            values.add(q.trim());
        }
        long total = jdbc.queryForObject("SELECT COUNT(*) FROM sys_login_log" + where, Long.class, values.toArray());
        values.add(pageSize);
        values.add((page - 1L) * pageSize);
        List<Map<String, Object>> items = jdbc.queryForList(
                "SELECT id,user_id,username,ip,status,message,login_at FROM sys_login_log" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                values.toArray());
        return Map.of("items", items, "total", total, "page", page, "pageSize", pageSize);
    }

    private static String blankOrNull(String value, int max) {
        if (value == null || value.isBlank()) return null;
        String trimmed = value.trim();
        return trimmed.length() <= max ? trimmed : trimmed.substring(0, max);
    }
}
