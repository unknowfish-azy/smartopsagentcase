package com.smartops.security;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * 生产环境安全断言（SEC-15 / Phase 1.2）。
 *
 * <p>只做"配置自相矛盾即拒绝启动"的判断，不改变任何运行时行为：
 * 生产环境开启 internal-bypass、内部 token 缺失/过短、聊天 run token 机密缺失，
 * 都会让平台落在"看起来可用、实际鉴权被绕过"的状态，必须在启动阶段暴露。</p>
 */
public final class SecurityAssertions {

    public static final int MIN_SECRET_LENGTH = 16;

    private SecurityAssertions() {
    }

    /**
     * 生产环境不满足安全配置时抛 {@link IllegalStateException}，由 Spring 启动失败；
     * 非生产环境直接放行（是否告警由调用方决定）。
     */
    public static void verify(boolean production,
                              boolean internalBypass,
                              String internalToken,
                              String chatRunTokenSecret) {
        if (!production) return;
        List<String> failures = new ArrayList<>();
        if (internalBypass) {
            failures.add("SMARTOPS_INTERNAL_BYPASS 必须为 false（当前为 true，等于关闭内部 token 校验）");
        }
        if (isBlank(internalToken)) {
            failures.add("SMARTOPS_INTERNAL_TOKEN 未配置");
        } else if (internalToken.trim().length() < MIN_SECRET_LENGTH) {
            failures.add("SMARTOPS_INTERNAL_TOKEN 长度不足 " + MIN_SECRET_LENGTH + " 字符");
        }
        if (isBlank(chatRunTokenSecret)) {
            failures.add("SMARTOPS_CHAT_RUN_TOKEN_SECRET 未配置（聊天会被 ai-service 全部拒绝）");
        } else if (chatRunTokenSecret.trim().length() < MIN_SECRET_LENGTH) {
            failures.add("SMARTOPS_CHAT_RUN_TOKEN_SECRET 长度不足 " + MIN_SECRET_LENGTH + " 字符");
        }
        if (!failures.isEmpty()) {
            throw new IllegalStateException("SECURITY_ASSERTION_FAILED: " + String.join("; ", failures));
        }
    }

    /** SEC-13：已知默认/弱口令黑名单（compose 示例值与常见弱口令）。 */
    private static final List<String> KNOWN_DEFAULT_PASSWORDS = List.of(
            "change-me-password", "change-me-root-password", "root", "password", "123456", "admin");

    /**
     * SEC-13：生产环境部署凭据断言——数据源/Redis 密码与附件加密 key 缺失或等于
     * 已知默认值时拒绝启动。只读配置做判断，不改运行时行为。
     */
    public static void verifyDeploymentSecrets(boolean production,
                                               String datasourcePassword,
                                               String redisPassword,
                                               String apiKeyEncryptionKey) {
        if (!production) return;
        List<String> failures = new ArrayList<>();
        if (isBlank(datasourcePassword)) {
            failures.add("MYSQL_PASSWORD 未配置（生产数据源不允许空密码）");
        } else if (KNOWN_DEFAULT_PASSWORDS.contains(datasourcePassword.trim())) {
            failures.add("MYSQL_PASSWORD 是已知默认口令（change-me/常见弱口令），必须替换");
        }
        if (isBlank(redisPassword)) {
            failures.add("REDIS_PASSWORD 未配置（生产 Redis 必须启用 requirepass）");
        } else if (KNOWN_DEFAULT_PASSWORDS.contains(redisPassword.trim())) {
            failures.add("REDIS_PASSWORD 是已知默认口令（change-me/常见弱口令），必须替换");
        }
        if (isBlank(apiKeyEncryptionKey)) {
            failures.add("SMARTOPS_API_KEY_ENCRYPTION_KEY 未配置（附件/凭据加密 key 不允许为空）");
        }
        if (!failures.isEmpty()) {
            throw new IllegalStateException("SECURITY_ASSERTION_FAILED: " + String.join("; ", failures));
        }
    }

    /**
     * 生产判定：显式开关优先，否则看激活 profile 是否包含 prod/production。
     */
    public static boolean isProduction(List<String> activeProfiles, boolean explicitProduction) {
        if (explicitProduction) return true;
        if (activeProfiles == null) return false;
        return activeProfiles.stream()
                .filter(profile -> profile != null && !profile.isBlank())
                .map(profile -> profile.trim().toLowerCase(Locale.ROOT))
                .anyMatch(profile -> profile.equals("prod") || profile.equals("production"));
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
