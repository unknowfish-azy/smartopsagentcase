package com.smartops.sentinel;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import javax.sql.DataSource;

/**
 * 哨兵模块的 schema 初始化与调度开关。
 *
 * <p>沿用项目既有模式（与 {@code AdminMfaConfig} 一致）：用
 * {@link ResourceDatabasePopulator} 执行幂等迁移脚本，不引入额外迁移框架。</p>
 *
 * <p>调度用 {@code @EnableScheduling} 显式开启，因为此前项目没有任何
 * {@code @Scheduled} 使用；开启范围仅限哨兵轮询，不影响其它模块。</p>
 */
@Configuration
@org.springframework.scheduling.annotation.EnableScheduling
public class SentinelConfig {

    /** 建表脚本：全部 IF NOT EXISTS，可重复执行。 */
    private static final String[] CREATE_SCRIPTS = {
            "db/migration/V20261011__sentinel.sql",
            "db/migration/V20261012__sentinel_knowledge.sql",
            "db/migration/V20261013__sentinel_script_schedule.sql"
    };

    @Bean
    InitializingBean sentinelSchema(DataSource source) {
        return () -> {
            for (String location : CREATE_SCRIPTS) {
                ResourceDatabasePopulator populator = new ResourceDatabasePopulator(new ClassPathResource(location));
                populator.setContinueOnError(false);
                populator.execute(source);
            }
            // 加列脚本不是幂等语句（H2/MySQL 都没有通用的 ADD COLUMN IF NOT EXISTS），
            // 因此先探测再执行，重复启动与已手工加过列的库都不会失败。
            JdbcTemplate jdbc = new JdbcTemplate(source);
            if (!hasColumn(jdbc, "sentinel_task", "group_label")) {
                new ResourceDatabasePopulator(
                        new ClassPathResource("db/migration/V20261016__sentinel_task_group.sql")).execute(source);
            }
            if (!hasColumn(jdbc, "sentinel_alert_rule", "email_to")) {
                new ResourceDatabasePopulator(
                        new ClassPathResource("db/migration/V20261017__sentinel_rule_email.sql")).execute(source);
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

    // 不在这里再声明 Clock：项目已由 AdminMfaConfig 提供 mfaClock，
    // 多一个同类型 bean 会让按类型注入变得有歧义（曾导致应用启动失败）。
    // SentinelService 用 @Qualifier("mfaClock") 显式引用既有 bean。
}
