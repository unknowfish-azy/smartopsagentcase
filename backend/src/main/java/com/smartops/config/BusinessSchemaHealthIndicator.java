package com.smartops.config;

import org.springframework.boot.actuate.health.AbstractHealthIndicator;
import org.springframework.boot.actuate.health.Health;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

@Component("businessSchema")
public class BusinessSchemaHealthIndicator extends AbstractHealthIndicator {
    private final JdbcTemplate jdbc;
    public BusinessSchemaHealthIndicator(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public List<String> missingTables() {
        List<String> missing = new ArrayList<>();
        for (String table : List.of("app_user", "model_connections", "operation_session_group", "operation_credential", "operation_session", "operation_known_host", "operation_tunnel", "operation_transfer", "operation_command", "operation_audit_event", "operation_run_record", "knowledge_candidate")) {
            try { jdbc.queryForList("SELECT 1 FROM " + table + " WHERE 1=0"); }
            catch (org.springframework.dao.DataAccessException error) { missing.add(table); }
        }
        return missing;
    }

    @Override protected void doHealthCheck(Health.Builder builder) {
        List<String> missing = missingTables();
        if (missing.isEmpty()) builder.up(); else builder.down();
        builder.withDetail("unavailableTables", missing);
    }
}
