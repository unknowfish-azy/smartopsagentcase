package com.smartops.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

@Component
public class HumanVerificationSettings {
    final boolean enabled;
    final String siteKey;
    final String secretKey;
    final Set<String> hostnames;
    final long minResponseMillis;
    /**
     * 普通用户层登录是否**每次都要**验证。
     *
     * <p>默认 true：两个入口行为对齐，用户层登录也要完成一次图形点选，
     * 而不是"平时不验证、失败三次才验证"—— 后者会让正常用户第一次遇到验证时
     * 对突然出现的验证框感到意外。设为 false 可退回按风险触发。</p>
     */
    final boolean alwaysRequireLogin;

    public HumanVerificationSettings(
            @Value("${smartops.security.human-verification.enabled:true}") boolean enabled,
            @Value("${smartops.security.human-verification.site-key:}") String siteKey,
            @Value("${smartops.security.human-verification.secret-key:}") String secretKey,
            @Value("${smartops.security.human-verification.hostnames:}") String hostnames,
            @Value("${smartops.security.human-verification.min-response-ms:600}") long minResponseMillis,
            @Value("${smartops.security.human-verification.always-require-login:true}") boolean alwaysRequireLogin,
            Environment environment) {
        boolean development = environment.acceptsProfiles(Profiles.of("dev", "test", "local"))
                && !environment.acceptsProfiles(Profiles.of("prod"));
        if (!enabled && !development) throw new IllegalStateException("Human verification may only be disabled in dev/test");
        if (!development && (testKey(siteKey) || testKey(secretKey))) {
            throw new IllegalStateException("Human verification test keys are forbidden outside dev/test");
        }
        this.enabled = enabled;
        this.siteKey = siteKey.trim();
        this.secretKey = secretKey.trim();
        this.minResponseMillis = Math.max(0, minResponseMillis);
        this.alwaysRequireLogin = alwaysRequireLogin;
        this.hostnames = Arrays.stream(hostnames.split(",")).map(String::trim)
                .map(value -> value.toLowerCase(Locale.ROOT)).filter(value -> !value.isEmpty()).collect(Collectors.toUnmodifiableSet());
    }

    boolean available() {
        return !siteKey.isBlank() && !secretKey.isBlank() && !hostnames.isEmpty()
                && hostnames.stream().allMatch(host -> host.matches("[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?"));
    }

    /**
     * 当前生效的供应商：配置齐备的 Turnstile 优先，否则退回离线本地图形验证。
     * 由配置切换而不是删除 Turnstile —— 配置了 site-key / secret-key / hostnames 时行为与改造前完全一致。
     */
    String providerKind() {
        return available() ? "turnstile" : LocalGraphicalVerificationProvider.PROVIDER;
    }

    private static boolean testKey(String value) {
        return value.trim().matches("[123]x0{15,}.*");
    }
}
