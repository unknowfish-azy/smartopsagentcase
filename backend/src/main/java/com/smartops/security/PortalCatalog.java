package com.smartops.security;

import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.Set;

/**
 * 门户注册中心：所有「入口层面」的唯一事实来源。
 *
 * <p>历史上 portal 的合法取值、角色映射、权限、空闲时长、限流策略散落在
 * {@code UserAccountService} 与 {@code AuthController} 的硬编码分支里。新增一个平级门户
 * 意味着要同时改 N 处，极易漏改造成鉴权缺口。这里把它们收敛为一张注册表：
 * 新增门户 = 加一条 {@link PortalSpec}，鉴权链路自动跟随。</p>
 *
 * <p>前端维护同构的 {@code portalCatalog.js}，两侧保持一致。</p>
 */
@Component
public class PortalCatalog {

    /** 单个门户的完整规约。 */
    public record PortalSpec(
            String id,          // portal 标识，与前端 ?portal= 一致
            String label,       // 中文展示名
            String role,        // 该门户要求的账号角色（app_user.role）
            String authority,   // 登录成功后授予的 Spring Authority（含 ROLE_ 前缀）
            int idleSeconds,    // 会话空闲超时时长（秒）
            boolean pub,        // 是否在用户层登录页公开暴露入口
            boolean sensitive,  // 是否高敏：强制 MFA + 更严登录限流
            int rateLimit,      // 该门户登录失败限流次数
            long rateWindowSec  // 限流窗口（秒）
    ) {}

    private static final Map<String, PortalSpec> REGISTRY = Map.of(
            "user",       new PortalSpec("user",       "用户层",     "operator",   "ROLE_OPERATOR",   1800, true,  false, 10, 300),
            "admin",      new PortalSpec("admin",      "管理层",     "admin",      "ROLE_ADMIN",      600,  false, true,   5, 900),
            "enterprise", new PortalSpec("enterprise", "企业管理层", "enterprise", "ROLE_ENTERPRISE", 900,  false, false, 10, 300),
            "audit",      new PortalSpec("audit",      "审计合规层", "auditor",    "ROLE_AUDIT",      600,  false, true,   5, 900),
            "command",    new PortalSpec("command",    "决策指挥层", "commander",  "ROLE_COMMAND",    600,  false, true,   5, 900),
            "open",       new PortalSpec("open",       "开放生态层", "partner",    "ROLE_OPEN",       1800, false, false, 10, 300)
    );

    /** 登录失败限流：高敏/管理态更严（5 次 / 900 秒），普通态更宽（10 次 / 300 秒）。 */
    public record RateLimit(int attempts, long windowSeconds) {}
    private static final RateLimit ADMINISTRATIVE_LIMIT = new RateLimit(5, 900);
    private static final RateLimit DEFAULT_LIMIT = new RateLimit(10, 300);

    /** portal 是否为已注册的合法入口。未知 portal 一律 fail-closed。 */
    public boolean isAllowed(String portal) {
        return portal != null && REGISTRY.containsKey(portal);
    }

    public PortalSpec spec(String portal) {
        return REGISTRY.get(portal);
    }

    public Set<String> allowed() {
        return REGISTRY.keySet();
    }

    /** 该门户要求的账号角色；未知 portal 返回 null。 */
    public String roleOf(String portal) {
        PortalSpec spec = spec(portal);
        return spec == null ? null : spec.role();
    }

    /** 登录成功后授予的 Spring Authority；未知 portal 返回 null。 */
    public String authorityOf(String portal) {
        PortalSpec spec = spec(portal);
        return spec == null ? null : spec.authority();
    }

    public int idleSecondsOf(String portal) {
        PortalSpec spec = spec(portal);
        // 与历史行为一致：非管理态默认 1800 秒。
        return spec == null ? 1800 : spec.idleSeconds();
    }

    public boolean isPublic(String portal) {
        PortalSpec spec = spec(portal);
        return spec != null && spec.pub();
    }

    /** 高敏门户：强制 MFA、更严限流、更强密码（管理层 / 审计合规层 / 决策指挥层）。 */
    public boolean isSensitive(String portal) {
        PortalSpec spec = spec(portal);
        return spec != null && spec.sensitive();
    }

    /** 账号角色是否合法：必须是某个已注册门户规约的角色。 */
    public boolean isValidRole(String role) {
        if (role == null) return false;
        for (PortalSpec spec : REGISTRY.values()) if (spec.role().equals(role)) return true;
        return false;
    }

    /** 该角色是否属于高敏门户（决定强密码策略等）。 */
    public boolean isSensitiveRole(String role) {
        if (role == null) return false;
        for (PortalSpec spec : REGISTRY.values()) if (spec.role().equals(role) && spec.sensitive()) return true;
        return false;
    }

    /** IP 维度限流：按门户是否高敏决定。 */
    public RateLimit rateLimitForPortal(String portal) {
        return isSensitive(portal) ? ADMINISTRATIVE_LIMIT : DEFAULT_LIMIT;
    }

    /** 账号维度限流：administrative = 门户高敏 或 账号本身是管理员（与历史口径一致）。 */
    public RateLimit rateLimitForAccount(boolean administrative) {
        return administrative ? ADMINISTRATIVE_LIMIT : DEFAULT_LIMIT;
    }
}
