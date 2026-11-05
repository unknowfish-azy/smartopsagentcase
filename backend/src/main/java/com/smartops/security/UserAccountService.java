package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.nio.charset.StandardCharsets;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Locale;

@Service
public class UserAccountService {
    private static final String ACCOUNT_SQL = "SELECT u.id,u.username,u.role,u.enabled,u.password_hash,u.created_at,u.dept_id,u.post_id,u.real_name,u.phone,u.email,COALESCE(s.auth_version,0) AS auth_version,COALESCE(s.must_change_password,FALSE) AS must_change_password FROM app_user u LEFT JOIN account_security s ON s.user_id=u.id";
    private final JdbcTemplate jdbc;
    private final SecurityAuditService audit;
    private final AccountSessionRegistry sessions;
    private final BCryptPasswordEncoder passwords = new BCryptPasswordEncoder(12);
    private final String dummyHash = passwords.encode("unused-password-for-timing");
    private final AccountAttemptLimiter attempts = new AccountAttemptLimiter();

    public UserAccountService(JdbcTemplate jdbc, SecurityAuditService audit, AccountSessionRegistry sessions) {
        this.jdbc = jdbc; this.audit = audit; this.sessions = sessions;
    }

    public SessionUser authenticate(String username, String password, String address, String requestedPortal) {
        String portal = requestedPortal == null ? "user" : requestedPortal;
        if (!List.of("user", "admin").contains(portal)) throw new BusinessException(400, "登录入口无效");
        String ipKey = "login-ip:" + portal + ":" + address;
        int limit = portal.equals("admin") ? 5 : 10;
        long window = portal.equals("admin") ? 900 : 300;
        attempts.consume(ipKey, limit, window);
        var accounts = jdbc.query(ACCOUNT_SQL + " WHERE u.username=?", this::readAccount, username);
        Account account = accounts.isEmpty() ? null : accounts.get(0);
        String accountKey = "login-account:" + (account == null ? "unknown:" + normalizedName(username) : account.id);
        boolean administrative = portal.equals("admin") || (account != null && "admin".equals(account.role));
        attempts.consume(accountKey, administrative ? 5 : 10, administrative ? 900 : 300);
        boolean valid = matches(password, account == null ? dummyHash : account.hash);
        if (account == null || !account.enabled || !valid) {
            throw new BusinessException(401, "账号或密码错误");
        }
        if (portal.equals("admin") && !account.role.equals("admin")) throw new BusinessException(403, "此账号无管理员入口权限，请选择用户层登录");
        if (portal.equals("user") && account.role.equals("admin")) {
            throw new BusinessException(403, "\u7ba1\u7406\u5458\u8d26\u53f7\u5fc5\u987b\u9009\u62e9\u7ba1\u7406\u5458\u5c42\u767b\u5f55");
        }
        attempts.clear(ipKey);
        attempts.clear(accountKey);
        return new SessionUser(account.id, account.username, account.role, portal, account.mustChangePassword, account.authVersion);
    }

    public RegistrationPolicy registrationPolicy() {
        boolean enabled = Boolean.TRUE.equals(jdbc.queryForObject("SELECT enabled FROM registration_policy WHERE id=1", Boolean.class));
        return new RegistrationPolicy(enabled, 3, 12, 16, 72);
    }

    @Transactional
    public AccountView register(String username, String password, String confirmPassword, String address) {
        attempts.consume("registration-ip:" + address, 5, 600);
        attempts.consume("registration-global", 100, 60);
        boolean enabled = Boolean.TRUE.equals(jdbc.queryForObject("SELECT enabled FROM registration_policy WHERE id=1 FOR UPDATE", Boolean.class));
        if (!enabled) throw new BusinessException(403, "当前已关闭新用户注册，请联系管理员");
        if (password == null || !password.equals(confirmPassword)) throw new BusinessException(400, "两次输入的密码不一致");
        return createAccount(username, password, "operator", false, null);
    }

    @Transactional
    public RegistrationPolicy setRegistration(boolean enabled, SessionUser actor) {
        requireMutationAuthority(actor, true);
        jdbc.queryForObject("SELECT enabled FROM registration_policy WHERE id=1 FOR UPDATE", Boolean.class);
        jdbc.update("UPDATE registration_policy SET enabled=? WHERE id=1", enabled);
        audit.record(actor, "REGISTRATION_POLICY", enabled ? "enabled" : "disabled", "SUCCESS");
        return registrationPolicy();
    }

    public void confirmAdministration(SessionUser actor, String password, String address) {
        if (actor == null || !"admin".equals(actor.role()) || !"admin".equals(actor.portal()) || actor.mustChangePassword() || !isCurrent(actor)) {
            throw new BusinessException(403, "需要有效的管理员层会话");
        }
        if (password == null || password.isBlank()) throw new BusinessException(403, "ADMIN_CONFIRMATION_REQUIRED：请输入当前管理员密码确认操作");
        try {
            verifyCurrentPassword(requireAccount(actor.id()), password, address, 403);
        } catch (BusinessException rejected) {
            audit.record(actor, "ADMIN_VERIFY", actor.id().toString(), "FAILURE");
            throw rejected;
        }
        audit.record(actor, "ADMIN_VERIFY", actor.id().toString(), "SUCCESS");
    }

    private String normalizedName(String username) { return username == null ? "" : username.strip().toLowerCase(Locale.ROOT); }

    private void verifyCurrentPassword(Account account, String password, String address, int failureStatus) {
        boolean administrative = "admin".equals(account.role);
        String ipKey = "password-check-ip:" + account.role + ":" + address;
        String accountKey = "password-check-account:" + account.id;
        attempts.consume(ipKey, administrative ? 5 : 10, administrative ? 900 : 300);
        attempts.consume(accountKey, administrative ? 5 : 10, administrative ? 900 : 300);
        if (!matches(password, account.hash)) throw new BusinessException(failureStatus, "当前" + (failureStatus == 403 ? "管理员" : "") + "密码不正确，操作未执行");
        attempts.clear(ipKey);
        attempts.clear(accountKey);
    }

    public boolean isCurrent(SessionUser user) {
        var accounts = jdbc.query(ACCOUNT_SQL + " WHERE u.id=?", this::readAccount, user.id());
        if (accounts.isEmpty()) return false;
        Account account = accounts.get(0);
        return account.enabled && account.authVersion == user.authVersion() && account.role.equals(user.role())
                && account.mustChangePassword == user.mustChangePassword() && (!"admin".equals(user.portal()) || "admin".equals(account.role));
    }

    public boolean hasPlatformCapability(SessionUser actor, String capability) {
        if (actor == null || !"admin".equals(actor.role()) || !"admin".equals(actor.portal()) || capability == null) return false;
        List<PlatformProfile> profiles = profileOf(actor.id());
        // 治理迁移前创建的管理员没有档案，沿用历史语义视为最高管理员。
        if (profiles.isEmpty()) return true;
        // 已撤销的管理员档案保留：不得因为缺少能力行而被重新放行。
        if (profiles.get(0).revoked()) return false;
        return jdbc.queryForObject("SELECT COUNT(*) FROM platform_admin_capability WHERE user_id=? AND capability=?", Integer.class, actor.id(), capability) > 0;
    }

    private record PlatformProfile(String level, java.sql.Timestamp revokedAt) {
        boolean revoked() { return revokedAt != null; }
    }

    private List<PlatformProfile> profileOf(long userId) {
        try {
            return jdbc.query("SELECT level,revoked_at FROM platform_admin_profile WHERE user_id=?",
                    (result, row) -> new PlatformProfile(result.getString("level"), result.getTimestamp("revoked_at")), userId);
        } catch (org.springframework.dao.DataAccessException unavailable) {
            // 读不到治理表时不能假定为 root，否则会把部署故障变成提权。
            throw new BusinessException(500, "平台治理数据不可用，请联系系统管理员");
        }
    }

    public void requirePlatformCapability(SessionUser actor, String capability) {
        if (!hasPlatformCapability(actor, capability)) throw new BusinessException(403, "平台权限不足：" + capability);
    }

    /** 多个能力中任一即可的显式组合规则；不用“角色取并集”隐式放宽。 */
    public void requireAnyPlatformCapability(SessionUser actor, String... capabilities) {
        for (String capability : capabilities) if (hasPlatformCapability(actor, capability)) return;
        throw new BusinessException(403, "平台权限不足：" + String.join("|", capabilities));
    }

    /** 能力目录：服务端给出级别、可任命级别与可转授能力，前端不再自行拼装。 */
    public CapabilityCatalog capabilityCatalog(SessionUser actor) {
        requirePlatformCapability(actor, "admin.users");
        String level = platformLevel(actor);
        var manageable = new ArrayList<String>();
        if (PlatformAdminGovernance.ROOT.equals(level)) {
            manageable.add(PlatformAdminGovernance.DEPUTY);
            manageable.add(PlatformAdminGovernance.SPECIALIST);
        } else if (PlatformAdminGovernance.DEPUTY.equals(level)) {
            manageable.add(PlatformAdminGovernance.SPECIALIST);
        }
        var items = PlatformAdminGovernance.ROOT_CAPABILITIES.stream().sorted()
                .map(capability -> new CapabilityView(capability, PlatformAdminGovernance.label(capability), PlatformAdminGovernance.canGrant(level, capability)))
                .toList();
        return new CapabilityCatalog(level, manageable, items);
    }

    /**
     * 账户上下文：组织归属、系统角色、平台管理员档案、活动会话与近期审计元数据。
     * 只汇总治理元数据，不返回私人知识、聊天正文或连接凭据。
     */
    public AccountContext accountContext(SessionUser actor, long id) {
        requirePlatformCapability(actor, "admin.users");
        Account account = requireAccount(id);
        var chain = new ArrayList<String>();
        Long deptId = account.deptId();
        while (deptId != null && chain.size() < 10) {
            var rows = jdbc.queryForList("SELECT name,parent_id FROM sys_dept WHERE id=?", deptId);
            if (rows.isEmpty()) break;
            chain.add(0, String.valueOf(rows.get(0).get("name")));
            Object parent = rows.get(0).get("parent_id");
            deptId = parent == null ? null : ((Number) parent).longValue();
        }
        String postName = account.postId() == null ? null
                : jdbc.query("SELECT name FROM sys_post WHERE id=?", (result, row) -> result.getString(1), account.postId()).stream().findFirst().orElse(null);
        var rbacRoles = jdbc.query("SELECT r.id,r.name,r.code,r.data_scope,r.status FROM sys_role r JOIN sys_user_role ur ON ur.role_id=r.id WHERE ur.user_id=? ORDER BY r.id",
                (result, row) -> new RbacRoleView(result.getLong("id"), result.getString("name"), result.getString("code"), result.getInt("data_scope"), result.getInt("status")), id);
        List<PlatformProfile> profiles = profileOf(id);
        PlatformAdminContext platform = profiles.isEmpty() ? new PlatformAdminContext(false, null, false, null, List.of())
                : new PlatformAdminContext(true, profiles.get(0).level(), profiles.get(0).revoked(), appointedAt(id), capabilitiesOf(id));
        long enabledAdmins = count("SELECT COUNT(*) FROM app_user WHERE role='admin' AND enabled=TRUE");
        boolean lastAdmin = "admin".equals(account.role()) && account.enabled() && enabledAdmins <= 1;
        var recentAudit = jdbc.query("SELECT id,actor_username,action,outcome,detail,created_at FROM security_audit_event WHERE actor_id=? OR target_id=? ORDER BY id DESC LIMIT 20",
                (result, row) -> new AuditLite(result.getLong("id"), result.getString("actor_username"), result.getString("action"), result.getString("outcome"), result.getString("detail"), result.getTimestamp("created_at").toInstant().toString()),
                id, Long.toString(id));
        return new AccountContext(viewOf(account), chain.isEmpty() ? null : String.join(" / ", chain), postName, rbacRoles, platform,
                sessions.list(id, null), new ProtectionView(actor != null && actor.id() == id, lastAdmin), recentAudit);
    }

    private String appointedAt(long userId) {
        return jdbc.query("SELECT appointed_at FROM platform_admin_profile WHERE user_id=?", (result, row) -> {
            Timestamp value = result.getTimestamp(1);
            return value == null ? null : value.toInstant().toString();
        }, userId).stream().findFirst().orElse(null);
    }

    private List<String> capabilitiesOf(long userId) {
        return jdbc.query("SELECT capability FROM platform_admin_capability WHERE user_id=? ORDER BY capability", (result, row) -> result.getString(1), userId);
    }

    public List<PlatformAdminView> platformAdministrators(SessionUser actor) {
        requirePlatformCapability(actor, "admin.users");
        try {
            return jdbc.query("SELECT u.id,u.username,u.enabled,p.level,COALESCE(GROUP_CONCAT(c.capability), '') capabilities FROM app_user u JOIN platform_admin_profile p ON p.user_id=u.id LEFT JOIN platform_admin_capability c ON c.user_id=u.id WHERE u.role='admin' AND p.revoked_at IS NULL GROUP BY u.id,u.username,u.enabled,p.level ORDER BY CASE p.level WHEN 'root' THEN 0 WHEN 'deputy' THEN 1 ELSE 2 END,u.id",
                    (row, ignored) -> new PlatformAdminView(row.getLong("id"), row.getString("username"), row.getBoolean("enabled"), row.getString("level"), row.getString("capabilities").isBlank() ? List.of() : List.of(row.getString("capabilities").split(","))),
                    new Object[0]);
        } catch (org.springframework.dao.DataAccessException missingMigration) {
            return jdbc.query("SELECT id,username,enabled FROM app_user WHERE role='admin' ORDER BY id", (row, ignored) -> new PlatformAdminView(row.getLong("id"), row.getString("username"), row.getBoolean("enabled"), "root", List.of()), new Object[0]);
        }
    }

    @Transactional
    public PlatformAdminView appointPlatformAdmin(SessionUser actor, long targetId, String level, List<String> capabilities) {
        requireMutationAuthority(actor, true);
        if (!PlatformAdminGovernance.canManage(platformLevel(actor), level)) throw new BusinessException(403, "无权任命该级别管理员");
        if (targetId == actor.id()) throw new BusinessException(400, "不能修改自己的管理员级别");
        Account target = requireAccount(targetId);
        if (!"admin".equals(target.role)) throw new BusinessException(400, "目标账号必须先具备管理员入口");
        List<String> requested = capabilities == null ? List.of() : capabilities.stream().distinct().toList();
        if (requested.stream().anyMatch(capability -> !PlatformAdminGovernance.canGrant(platformLevel(actor), capability))) throw new BusinessException(403, "包含不可转授的平台能力");
        jdbc.update("INSERT INTO platform_admin_profile(user_id,level,appointed_by) VALUES(?,?,?) ON DUPLICATE KEY UPDATE level=VALUES(level),appointed_by=VALUES(appointed_by),appointed_at=CURRENT_TIMESTAMP,revoked_at=NULL", targetId, level, actor.id());
        jdbc.update("DELETE FROM platform_admin_capability WHERE user_id=?", targetId);
        requested.forEach(capability -> jdbc.update("INSERT INTO platform_admin_capability(user_id,capability,granted_by) VALUES(?,?,?)", targetId, capability, actor.id()));
        bumpVersion(targetId, target.mustChangePassword);
        audit.record(actor, "PLATFORM_ADMIN_APPOINT", targetId + ":" + level, "SUCCESS");
        revokeAfterCommit(targetId);
        return platformAdministrators(actor).stream().filter(item -> item.id() == targetId).findFirst().orElseThrow();
    }

    @Transactional
    public PlatformAdminView revokePlatformAdmin(SessionUser actor, long targetId) {
        requireMutationAuthority(actor, true);
        String actorLevel = platformLevel(actor);
        List<PlatformProfile> targetProfiles = profileOf(targetId);
        if (targetProfiles.isEmpty()) throw new BusinessException(409, "该账号没有平台管理员档案，无法撤销");
        if (targetProfiles.get(0).revoked()) throw new BusinessException(409, "该账号的平台权限已撤销");
        String targetLevel = targetProfiles.get(0).level();
        if (!PlatformAdminGovernance.canManage(actorLevel, targetLevel)) throw new BusinessException(403, "无权撤销该管理员");
        // 保留档案并写入撤销时间：直接删档会让“无档案=历史管理员”的历史语义把它重新放行。
        jdbc.update("UPDATE platform_admin_profile SET revoked_at=CURRENT_TIMESTAMP,appointed_by=? WHERE user_id=?", actor.id(), targetId);
        jdbc.update("DELETE FROM platform_admin_capability WHERE user_id=?", targetId);
        bumpVersion(targetId, true);
        audit.record(actor, "PLATFORM_ADMIN_REVOKE", Long.toString(targetId), "SUCCESS");
        revokeAfterCommit(targetId);
        Account revoked = requireAccount(targetId);
        return new PlatformAdminView(targetId, revoked.username, revoked.enabled, "none", List.of());
    }

    @Transactional
    public void transferPlatformRoot(SessionUser actor, long targetId) {
        requireMutationAuthority(actor, true);
        if (!PlatformAdminGovernance.ROOT.equals(platformLevel(actor))) throw new BusinessException(403, "只有最高管理员可以转让身份");
        if (targetId == actor.id()) throw new BusinessException(400, "不能转让给自己");
        Account target = requireAccount(targetId);
        if (!target.enabled || !"admin".equals(target.role())) throw new BusinessException(400, "接任者必须是启用的管理员账号");
        List<PlatformProfile> targetProfiles = profileOf(targetId);
        if (targetProfiles.isEmpty() || targetProfiles.get(0).revoked() || !PlatformAdminGovernance.DEPUTY.equals(targetProfiles.get(0).level()))
            throw new BusinessException(409, "接任者必须是未撤销的副管理员");
        jdbc.queryForObject("SELECT user_id FROM platform_admin_profile WHERE user_id=? FOR UPDATE", Long.class, actor.id());
        jdbc.queryForObject("SELECT user_id FROM platform_admin_profile WHERE user_id=? FOR UPDATE", Long.class, targetId);
        jdbc.update("UPDATE platform_admin_profile SET level='deputy',appointed_by=? WHERE user_id=?", actor.id(), actor.id());
        jdbc.update("UPDATE platform_admin_profile SET level='root',appointed_by=? WHERE user_id=?", actor.id(), targetId);
        jdbc.update("DELETE FROM platform_admin_capability WHERE user_id=?", targetId);
        PlatformAdminGovernance.ROOT_CAPABILITIES.forEach(capability -> jdbc.update("INSERT INTO platform_admin_capability(user_id,capability,granted_by) VALUES(?,?,?)", targetId, capability, actor.id()));
        bumpVersion(actor.id(), false); bumpVersion(targetId, target.mustChangePassword);
        audit.record(actor, "PLATFORM_ROOT_TRANSFER", targetId + ":" + actor.id(), "SUCCESS");
        revokeAfterCommit(actor.id()); revokeAfterCommit(targetId);
    }

    private String platformLevel(SessionUser actor) {
        List<PlatformProfile> profiles = profileOf(actor.id());
        // 治理建档前的存量管理员没有档案，按历史语义视为最高管理员。
        return profiles.isEmpty() ? PlatformAdminGovernance.ROOT : profiles.get(0).level();
    }

    public AccountPage list(String query, String role, Boolean enabled, int page, int pageSize) {
        SecurityAuditService.validatePage(page, pageSize);
        var values = new ArrayList<Object>();
        StringBuilder where = new StringBuilder(" WHERE 1=1");
        if (query != null && !query.isBlank()) {
            if (query.length() > 64) throw new BusinessException(400, "搜索内容不能超过 64 个字符");
            where.append(" AND LOCATE(LOWER(?),LOWER(u.username))>0"); values.add(query.trim());
        }
        if (role != null && !role.isBlank()) { validateRole(role); where.append(" AND u.role=?"); values.add(role); }
        if (enabled != null) { where.append(" AND u.enabled=?"); values.add(enabled); }
        long total = jdbc.queryForObject("SELECT COUNT(*) FROM app_user u" + where, Long.class, values.toArray());
        values.add(pageSize); values.add((page - 1L) * pageSize);
        var items = jdbc.query(ACCOUNT_SQL + where + " ORDER BY u.id LIMIT ? OFFSET ?", this::readAccount, values.toArray()).stream().map(this::viewOf).toList();
        return new AccountPage(items, total, page, pageSize);
    }

    @Transactional
    public AccountView create(String username, String password, String role, Long deptId, Long postId, List<Long> roleIds, SessionUser actor) {
        requireMutationAuthority(actor, true);
        return createAccount(username, password, role, true, deptId, postId, roleIds, actor);
    }

    private AccountView createAccount(String username, String password, String role, boolean mustChange, SessionUser actor) {
        return createAccount(username, password, role, mustChange, null, null, null, actor);
    }

    private AccountView createAccount(String username, String password, String role, boolean mustChange, Long deptId, Long postId, List<Long> roleIds, SessionUser actor) {
        if (username == null || !username.matches("[A-Za-z0-9_.-]{3,64}")) throw new BusinessException(400, "账号需为 3–64 位字母、数字、点、下划线或短横线");
        validateRole(role); validatePassword(password, role);
        validateDeptPost(deptId, postId); validateRoleIds(roleIds);
        try {
            jdbc.update("INSERT INTO app_user(username,password_hash,role,dept_id,post_id) VALUES(?,?,?,?,?)",
                    username, passwords.encode(password), role, deptId, postId);
        } catch (DuplicateKeyException error) { throw new BusinessException(409, "账号已存在"); }
        long id = jdbc.queryForObject("SELECT id FROM app_user WHERE username=?", Long.class, username);
        jdbc.update("INSERT INTO account_security(user_id,must_change_password) VALUES(?,?)", id, mustChange);
        assignRoles(id, roleIds);
        audit.record(actor, actor == null && "operator".equals(role) ? "REGISTER" : "CREATE_USER", Long.toString(id), "SUCCESS");
        return viewOf(requireAccount(id));
    }

    @Transactional
    public AccountView update(long id, String role, boolean enabled, Long deptId, Long postId, List<Long> roleIds, SessionUser actor) {
        validateRole(role);
        validateDeptPost(deptId, postId); validateRoleIds(roleIds);
        var administrators = requireMutationAuthority(actor, true);
        Account account = requireAccount(id);
        if (account.role.equals("admin") && account.enabled && (!role.equals("admin") || !enabled) && administrators.size() <= 1) {
            throw new BusinessException(409, "至少保留一个启用的管理员，不能禁用或降权最后一个管理员");
        }
        boolean changed = false;
        if (!account.role.equals(role) || account.enabled != enabled) {
            jdbc.update("UPDATE app_user SET role=?,enabled=? WHERE id=?", role, enabled, id);
            bumpVersion(id, account.mustChangePassword || (!account.role.equals("admin") && role.equals("admin")));
            changed = true;
        }
        if (!java.util.Objects.equals(account.deptId, deptId) || !java.util.Objects.equals(account.postId, postId)) {
            jdbc.update("UPDATE app_user SET dept_id=?,post_id=? WHERE id=?", deptId, postId, id);
            changed = true;
        }
        assignRoles(id, roleIds);
        if (changed) {
            audit.record(actor, "UPDATE_USER", Long.toString(id), "SUCCESS");
            revokeAfterCommit(id);
        }
        return viewOf(requireAccount(id));
    }

    /** 校验部门/岗位存在；null 表示不绑定（清除）。 */
    private void validateDeptPost(Long deptId, Long postId) {
        if (deptId != null) {
            Integer c = jdbc.queryForObject("SELECT COUNT(*) FROM sys_dept WHERE id=?", Integer.class, deptId);
            if (c == null || c == 0) throw new BusinessException(400, "所选部门不存在");
        }
        if (postId != null) {
            Integer c = jdbc.queryForObject("SELECT COUNT(*) FROM sys_post WHERE id=?", Integer.class, postId);
            if (c == null || c == 0) throw new BusinessException(400, "所选岗位不存在");
        }
    }

    /** 校验 RBAC 角色存在；重复与未知都会被拒绝。 */
    private void validateRoleIds(List<Long> roleIds) {
        if (roleIds == null || roleIds.isEmpty()) return;
        List<Long> distinct = roleIds.stream().distinct().toList();
        for (long roleId : distinct) {
            Integer c = jdbc.queryForObject("SELECT COUNT(*) FROM sys_role WHERE id=?", Integer.class, roleId);
            if (c == null || c == 0) throw new BusinessException(400, "所选角色不存在");
        }
    }

    /** 整树替换用户 RBAC 角色（sys_user_role）。先清后插，同事务内无重复风险。 */
    private void assignRoles(long userId, List<Long> roleIds) {
        jdbc.update("DELETE FROM sys_user_role WHERE user_id=?", userId);
        if (roleIds != null) {
            for (long roleId : roleIds.stream().distinct().toList()) {
                jdbc.update("INSERT INTO sys_user_role(user_id,role_id) VALUES(?,?)", userId, roleId);
            }
        }
    }

    @Transactional
    public void resetPassword(long id, String password, SessionUser actor) {
        requireMutationAuthority(actor, true);
        Account account = requireAccount(id);
        validatePassword(password, account.role);
        if (matches(password, account.hash)) throw new BusinessException(400, "新密码不能与原密码相同");
        jdbc.update("UPDATE app_user SET password_hash=? WHERE id=?", passwords.encode(password), id);
        bumpVersion(id, true);
        audit.record(actor, "RESET_PASSWORD", Long.toString(id), "SUCCESS");
        revokeAfterCommit(id);
    }

    @Transactional
    public void changePassword(SessionUser actor, String currentPassword, String newPassword, String address) {
        lockAdministrators();
        Account account = requireAccount(actor.id());
        if (!account.enabled || account.authVersion != actor.authVersion()) throw new BusinessException(401, "会话已失效，请重新登录");
        validatePassword(newPassword, account.role);
        verifyCurrentPassword(account, currentPassword, address, 400);
        if (matches(newPassword, account.hash)) throw new BusinessException(400, "新密码不能与原密码相同");
        jdbc.update("UPDATE app_user SET password_hash=? WHERE id=?", passwords.encode(newPassword), actor.id());
        bumpVersion(actor.id(), false);
        audit.record(actor, "CHANGE_PASSWORD", actor.id().toString(), "SUCCESS");
        revokeAfterCommit(actor.id());
    }

    /** 当前账号的个人资料（姓名/电话/邮箱），自服务读取。 */
    public Map<String, String> profile(SessionUser actor) {
        Account account = requireAccount(actor.id());
        return Map.of("realName", nz(account.realName()), "phone", nz(account.phone()), "email", nz(account.email()));
    }

    /** 更新个人资料（自服务，不要求管理员复核，因为改的是自己而非他人）。 */
    @Transactional
    public Map<String, String> updateProfile(SessionUser actor, String realName, String phone, String email) {
        Account account = requireAccount(actor.id());
        if (!account.enabled || account.authVersion != actor.authVersion()) throw new BusinessException(401, "会话已失效，请重新登录");
        jdbc.update("UPDATE app_user SET real_name=?,phone=?,email=? WHERE id=?",
                clip(realName, 64), clip(phone, 32), clip(email, 128), actor.id());
        audit.record(actor, "PROFILE_UPDATE", Long.toString(actor.id()), "SUCCESS");
        return profile(actor);
    }

    private static String nz(String value) { return value == null ? "" : value; }
    private static String clip(String value, int max) {
        if (value == null || value.isBlank()) return null;
        String trimmed = value.trim();
        return trimmed.length() <= max ? trimmed : trimmed.substring(0, max);
    }

    public Map<String, Long> overview() {
        return Map.of("usersTotal", count("SELECT COUNT(*) FROM app_user"),
                "usersEnabled", count("SELECT COUNT(*) FROM app_user WHERE enabled=TRUE"),
                "adminsEnabled", count("SELECT COUNT(*) FROM app_user WHERE role='admin' AND enabled=TRUE"),
                "activeSessions", (long) sessions.list(null, null).size(),
                "pendingPasswordChanges", count("SELECT COUNT(*) FROM app_user u JOIN account_security s ON s.user_id=u.id WHERE u.enabled=TRUE AND s.must_change_password=TRUE"),
                "recentFailures", jdbc.queryForObject("SELECT COUNT(*) FROM security_audit_event WHERE action='LOGIN' AND outcome<>'SUCCESS' AND created_at>=?", Long.class, Timestamp.from(Instant.now().minusSeconds(86400))));
    }

    @Transactional
    public void bootstrap(String username, String password) {
        if (password == null || password.isBlank() || count("SELECT COUNT(*) FROM app_user") != 0) return;
        createAccount(username, password, "admin", false, null);
    }

    private long count(String sql) { return jdbc.queryForObject(sql, Long.class); }
    @Transactional(propagation = org.springframework.transaction.annotation.Propagation.MANDATORY)
    public List<Long> requireMutationAuthority(SessionUser actor, boolean management) {
        var administrators = lockAdministrators();
        if (actor == null || !isCurrent(actor)) throw new BusinessException(401, "账号权限或密码已变更，请重新登录");
        if (actor.mustChangePassword()) throw new BusinessException(403, "请先修改初始密码");
        if (management) requirePlatformCapability(actor, "admin.users");
        return administrators;
    }
    private List<Long> lockAdministrators() { return jdbc.queryForList("SELECT id FROM app_user WHERE role='admin' AND enabled=TRUE ORDER BY id FOR UPDATE", Long.class); }
    private Account requireAccount(long id) {
        var found = jdbc.query(ACCOUNT_SQL + " WHERE u.id=?", this::readAccount, id);
        if (found.isEmpty()) throw new BusinessException(404, "账号不存在");
        return found.get(0);
    }
    private void bumpVersion(long id, boolean mustChange) {
        jdbc.update("INSERT INTO account_security(user_id) SELECT ? WHERE NOT EXISTS (SELECT 1 FROM account_security WHERE user_id=?)", id, id);
        jdbc.update("UPDATE account_security SET auth_version=auth_version+1,must_change_password=? WHERE user_id=?", mustChange, id);
    }
    private void revokeAfterCommit(long userId) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() { sessions.revokeUser(userId); }
        });
    }
    private boolean matches(String password, String hash) {
        return password != null && password.getBytes(StandardCharsets.UTF_8).length <= 72 && passwords.matches(password, hash);
    }
    private void validateRole(String role) {
        if (role == null || !List.of("admin", "operator").contains(role)) throw new BusinessException(400, "角色无效");
    }
    private void validatePassword(String password, String role) {
        int minimum = "admin".equals(role) ? 16 : 12;
        if (password == null || password.length() < minimum || password.getBytes(StandardCharsets.UTF_8).length > 72) {
            throw new BusinessException(400, ("admin".equals(role) ? "管理员" : "用户") + "密码至少 " + minimum + " 个字符，UTF-8 编码不得超过 72 字节");
        }
    }
    private Account readAccount(ResultSet result, int row) throws SQLException {
        return new Account(result.getLong("id"), result.getString("username"), result.getString("role"), result.getBoolean("enabled"), result.getString("password_hash"), result.getBoolean("must_change_password"), result.getLong("auth_version"), result.getTimestamp("created_at").toInstant().toString(),
                result.getObject("dept_id", Long.class), result.getObject("post_id", Long.class), result.getString("real_name"), result.getString("phone"), result.getString("email"));
    }
    private record Account(long id, String username, String role, boolean enabled, String hash, boolean mustChangePassword, long authVersion, String createdAt,
                           Long deptId, Long postId, String realName, String phone, String email) {}
    /** 组装账户视图并补齐 RBAC 角色 id（sys_user_role）。 */
    private AccountView viewOf(Account a) {
        List<Long> roleIds = jdbc.query("SELECT role_id FROM sys_user_role WHERE user_id=? ORDER BY role_id", (r, i) -> r.getLong("role_id"), a.id());
        return new AccountView(a.id(), a.username(), a.role(), a.enabled(), a.mustChangePassword(), a.createdAt(),
                a.deptId(), a.postId(), a.realName(), a.phone(), a.email(), roleIds);
    }
    public record RegistrationPolicy(boolean enabled, int usernameMinLength, int userPasswordMinLength, int adminPasswordMinLength, int passwordMaxBytes) {}
    public record AccountView(long id, String username, String role, boolean enabled, boolean mustChangePassword, String createdAt,
                              Long deptId, Long postId, String realName, String phone, String email, List<Long> roleIds) {}
    public record AccountPage(List<AccountView> items, long total, int page, int pageSize) {}
    public record PlatformAdminView(long id, String username, boolean enabled, String level, List<String> capabilities) {}
    public record CapabilityView(String value, String label, boolean grantable) {}
    public record CapabilityCatalog(String level, List<String> manageableLevels, List<CapabilityView> items) {}
    public record RbacRoleView(long id, String name, String code, int dataScope, int status) {}
    public record PlatformAdminContext(boolean profiled, String level, boolean revoked, String appointedAt, List<String> capabilities) {}
    public record ProtectionView(boolean self, boolean lastEnabledAdmin) {}
    public record AuditLite(long id, String actorUsername, String action, String outcome, String detail, String createdAt) {}
    public record AccountContext(AccountView account, String deptPath, String postName, List<RbacRoleView> rbacRoles,
                                 PlatformAdminContext platformAdmin, List<AccountSessionRegistry.SessionView> sessions,
                                 ProtectionView protection, List<AuditLite> recentAudit) {}
}
