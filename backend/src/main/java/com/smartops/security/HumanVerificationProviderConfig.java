package com.smartops.security;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 人机验证供应商的装配：与配置同源，避免"配置选了本地图形、容器里注入的却是 Turnstile"这类错配。
 *
 * <ul>
 *   <li>配置了 site-key / secret-key / hostnames → Turnstile；</li>
 *   <li>未配置（本地开发默认）→ 离线本地图形点选验证，因此默认配置下验证真实可用。</li>
 * </ul>
 */
@Configuration
public class HumanVerificationProviderConfig {

    @Bean
    @ConditionalOnMissingBean(HumanVerificationProvider.class)
    HumanVerificationProvider humanVerificationProvider(HumanVerificationSettings settings) {
        if ("turnstile".equals(settings.providerKind())) return new TurnstileVerificationProvider(settings);
        return new LocalGraphicalVerificationProvider(settings);
    }
}
