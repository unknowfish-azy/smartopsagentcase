package com.smartops.config;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class ModelGatewaySchemaConfig {
    @Bean
    @ConditionalOnProperty(name = "smartops.model-gateway.initialize-schema", havingValue = "true", matchIfMissing = true)
    InitializingBean modelGatewaySchema(DataSource source) {
        return () -> {
            new ResourceDatabasePopulator(new ClassPathResource("db/migration/V20261004__model_gateway.sql")).execute(source);
            JdbcTemplate jdbc = new JdbcTemplate(source);
            addColumnIfMissing(jdbc, "failure_count INT NOT NULL DEFAULT 0");
            addColumnIfMissing(jdbc, "unhealthy_until TIMESTAMP NULL");
            addColumnIfMissing(jdbc, "last_checked_at TIMESTAMP NULL");
            addColumnIfMissing(jdbc, "last_error_code VARCHAR(40) NULL");
        };
    }

    private void addColumnIfMissing(JdbcTemplate jdbc, String definition) {
        try { jdbc.execute("ALTER TABLE model_gateway_route ADD COLUMN " + definition); }
        catch (RuntimeException ignored) { /* Existing installations already have the column. */ }
    }
}
