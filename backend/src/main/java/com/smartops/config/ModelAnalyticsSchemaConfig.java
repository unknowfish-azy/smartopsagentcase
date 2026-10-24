package com.smartops.config;

import javax.sql.DataSource;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

@Configuration
public class ModelAnalyticsSchemaConfig {
    @Bean
    @ConditionalOnProperty(name = "smartops.model-analytics.initialize-schema", havingValue = "true", matchIfMissing = true)
    InitializingBean modelAnalyticsSchema(DataSource source) {
        return () -> new ResourceDatabasePopulator(new ClassPathResource("db/model-analytics.sql")).execute(source);
    }
}
