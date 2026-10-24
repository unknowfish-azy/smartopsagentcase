package com.smartops.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.beans.factory.InitializingBean;

import javax.sql.DataSource;

@Configuration
public class TeamAgentConfig {
    @Bean
    public InitializingBean teamAgentSchema(DataSource source) {
        return () -> new ResourceDatabasePopulator(new ClassPathResource("db/migration/V20261003__team_agents.sql")).execute(source);
    }
}
