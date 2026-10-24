package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class OperatorMemoryServiceTest {
    private JdbcTemplate jdbc;
    private OperatorMemoryService service;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:operator-memory-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE operator_memory (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, incident_key VARCHAR(255) NOT NULL, memory_type VARCHAR(32) NOT NULL, preferred_action TEXT NOT NULL, source_refs TEXT, evidence_count INT NOT NULL, confidence DOUBLE NOT NULL, status VARCHAR(32) NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)");
        service = new OperatorMemoryService(jdbc);
    }

    @Test
    void recordsConfirmedMemoryAndMatchesOnlyActiveMemoryForCurrentUser() {
        var memory = service.recordConfirmed(1L, "nginx:502", "TOOL", "先查 upstream 状态", "trace-1");
        service.recordConfirmed(2L, "nginx:502", "TOOL", "private", "trace-2");
        assertThat(service.match(1L, "502")).extracting(OperatorMemoryService.Memory::id).containsExactly(memory.id());
        service.disable(1L, memory.id());
        assertThat(service.match(1L, "502")).isEmpty();
    }
}
