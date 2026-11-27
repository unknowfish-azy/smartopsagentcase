package com.smartops.config;

import com.smartops.security.UserAccountService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class UserAccountConfig {
    @Bean
    ApplicationRunner bootstrapAdministrator(UserAccountService accounts,
            @Value("${smartops.bootstrap.username:admin}") String username,
            // 不设代码内默认值：未注入引导口令时 UserAccountService.bootstrap 直接跳过建号（fail-closed）
            @Value("${smartops.bootstrap.password:}") String password) {
        return arguments -> accounts.bootstrap(username, password);
    }
}
