package com.smartops.config;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import javax.sql.DataSource;

@Configuration
public class TeamGovernanceSchemaConfig {
    @Bean
    @DependsOn({"teamWorkspaceSchema", "teamAgentSchema", "teamAgentRunSchema"})
    InitializingBean teamGovernanceSchema(DataSource source) {
        return () -> new ResourceDatabasePopulator(
                new ClassPathResource("db/migration/V20261006__team_governance.sql"),
                new ClassPathResource("db/migration/V20261008__team_activity_and_notifications.sql"),
                new ClassPathResource("db/migration/V20261009__team_resource_grants.sql"),
                new ClassPathResource("db/migration/V20261010__team_notifications.sql")
        ).execute(source);
    }
}
