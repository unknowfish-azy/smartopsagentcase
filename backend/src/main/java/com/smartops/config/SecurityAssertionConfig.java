package com.smartops.config;

import com.smartops.security.SecurityAssertions;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Arrays;
import java.util.List;

/**
 * 启动期安全断言：生产配置不安全时直接拒绝启动，而不是运行中才发现鉴权被绕过。
 */
@Configuration
public class SecurityAssertionConfig {

    private static final Logger log = LoggerFactory.getLogger(SecurityAssertionConfig.class);

    @Bean
    ApplicationRunner assertSecurityRuntime(
            @Value("${smartops.security.production:false}") boolean explicitProduction,
            @Value("${spring.profiles.active:}") String activeProfiles,
            @Value("${smartops.security.internal-bypass:false}") boolean internalBypass,
            @Value("${smartops.security.internal-token:}") String internalToken,
            @Value("${smartops.security.chat.run-token.secret:}") String chatRunTokenSecret) {
        return arguments -> {
            List<String> profiles = activeProfiles == null || activeProfiles.isBlank()
                    ? List.of()
                    : Arrays.asList(activeProfiles.split(","));
            boolean production = SecurityAssertions.isProduction(profiles, explicitProduction);
            SecurityAssertions.verify(production, internalBypass, internalToken, chatRunTokenSecret);
            if (!production && internalBypass) {
                log.warn("SECURITY: internal-bypass=true 仅允许本地调试；生产环境会拒绝启动");
            }
            log.info("SECURITY: 启动断言通过（production={}）", production);
        };
    }
}
