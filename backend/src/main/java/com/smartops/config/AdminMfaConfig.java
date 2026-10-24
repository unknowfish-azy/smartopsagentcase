package com.smartops.config;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import javax.sql.DataSource;
import java.time.Clock;

@Configuration
public class AdminMfaConfig {
    @Bean Clock mfaClock() { return Clock.systemUTC(); }
    @Bean InitializingBean adminMfaSchema(DataSource source) {
        return () -> new ResourceDatabasePopulator(new ClassPathResource("db/migration/V005__admin_mfa.sql")).execute(source);
    }
}
