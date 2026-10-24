package com.smartops.config;

import com.smartops.security.UserAccountService;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import javax.sql.DataSource;

@Configuration
public class UserAccountConfig {
    @Bean
    InitializingBean userAccountSchema(DataSource source) {
        return () -> new ResourceDatabasePopulator(new ClassPathResource("db/auth-schema.sql")).execute(source);
    }

    @Bean
    ApplicationRunner bootstrapAdministrator(UserAccountService accounts,
            @Value("${smartops.bootstrap.username:admin}") String username,
            @Value("${smartops.bootstrap.password:}") String password) {
        return arguments -> accounts.bootstrap(username, password);
    }
}
