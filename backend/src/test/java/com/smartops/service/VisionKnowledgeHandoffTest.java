package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class VisionKnowledgeHandoffTest {
    private JdbcTemplate jdbc;
    private VisionEventService service;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:vision-handoff-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE vision_event (id VARCHAR(36) PRIMARY KEY, conversation_id VARCHAR(36), attachment_id VARCHAR(36), user_id BIGINT NOT NULL, source_type VARCHAR(32), ocr_status VARCHAR(32), analysis_status VARCHAR(32), privacy_status VARCHAR(32), user_confirmed BOOLEAN, created_at BIGINT, updated_at BIGINT)");
        jdbc.update("INSERT INTO vision_event(id,user_id,ocr_status,analysis_status,privacy_status,user_confirmed) VALUES('v1',1,'READY','READY_FOR_ANALYSIS','CLEAR',FALSE)");
        service = new VisionEventService(jdbc);
    }

    @Test
    void requiresExplicitConfirmationBeforeHandoff() {
        assertThat(service.confirm(1L, "v1").userConfirmed()).isTrue();
        assertThatThrownBy(() -> service.confirm(2L, "v1")).hasMessage("VISION_EVENT_NOT_FOUND");
    }
}
