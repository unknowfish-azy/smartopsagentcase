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
            @Value("${smartops.bootstrap.password:}") String password) {
        return arguments -> accounts.bootstrap(username, password);
    }
}
