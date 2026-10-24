package com.smartops.config;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import javax.sql.DataSource;

/**
 * 企业级系统管理模块的 schema 初始化。
 *
 * <p>沿用项目既有模式：{@link ResourceDatabasePopulator} 执行幂等建表脚本，
 * 加列脚本由"先探测再执行"保证幂等（H2/MySQL 无通用 ADD COLUMN IF NOT EXISTS）。</p>
 *
 * <p>依赖 {@code userAccountSchema}（UserAccountConfig）：V20261019 会给 app_user 与
 * security_audit_event 加列，必须先等这两张表创建好。</p>
 */
@Configuration
public class SysAdminConfig {

    @Bean
    @DependsOn("userAccountSchema")
    InitializingBean sysAdminSchema(DataSource source) {
        return () -> {
            new ResourceDatabasePopulator(new ClassPathResource("db/migration/V20261018__sys_management.sql"))
                    .execute(source);
            JdbcTemplate jdbc = new JdbcTemplate(source);
            // app_user 扩展：部门/岗位/资料
            if (!hasColumn(jdbc, "app_user", "dept_id")) {
                new ResourceDatabasePopulator(new ClassPathResource("db/migration/V20261019__sys_extend_accounts.sql"))
                        .execute(source);
            }
            // 操作日志复用 security_audit_event，补充 IP 与详情两列
            if (!hasColumn(jdbc, "security_audit_event", "ip")) {
                new ResourceDatabasePopulator(new ClassPathResource("db/migration/V20261019__sys_extend_accounts.sql"))
                        .execute(source);
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
