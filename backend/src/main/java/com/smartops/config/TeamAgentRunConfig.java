package com.smartops.config;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import javax.sql.DataSource;

@Configuration
public class TeamAgentRunConfig {
    @Bean
    InitializingBean teamAgentRunSchema(DataSource source) {
        return () -> {
            new ResourceDatabasePopulator(new ClassPathResource("db/migration/V20261003__team_agent_runs.sql")).execute(source);
            JdbcTemplate jdbc = new JdbcTemplate(source);
            // 协作优化 1：审批附决策依据。
            if (!hasColumn(jdbc, "team_agent_run", "decision_basis")) {
                new ResourceDatabasePopulator(
                        new ClassPathResource("db/migration/V20261014__team_run_decision_basis.sql")).execute(source);
            }
            // 协作优化 2：草稿乐观锁。两列要么都加、要么都不加，避免半截状态。
            if (!hasColumn(jdbc, "team_agent_version", "revision")) {
                new ResourceDatabasePopulator(
                        new ClassPathResource("db/migration/V20261015__team_draft_revision.sql")).execute(source);
            }
        };
    }

    private static boolean hasColumn(JdbcTemplate jdbc, String table, String column) {
        Integer count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                 WHERE LOWER(TABLE_NAME)=? AND LOWER(COLUMN_NAME)=?
                """, Integer.class, table, column);
        return count != null && count > 0;
    }
}
