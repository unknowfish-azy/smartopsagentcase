package com.smartops.config;

import javax.sql.DataSource;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

@Configuration
public class TeamWorkspaceConfig {
    @Bean InitializingBean teamWorkspaceSchema(DataSource source) {
        return () -> new ResourceDatabasePopulator(new ClassPathResource("db/migration/V006__team_workspace.sql")).execute(source);
    }
}
