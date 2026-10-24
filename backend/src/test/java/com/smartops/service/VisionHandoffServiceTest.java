package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class VisionHandoffServiceTest {
    private JdbcTemplate jdbc;
    private VisionHandoffService service;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:vision-handoff-service-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE vision_event (id VARCHAR(36) PRIMARY KEY, user_id BIGINT NOT NULL, ocr_status VARCHAR(32), user_confirmed BOOLEAN, ocr_text CLOB)");
        jdbc.execute("CREATE TABLE personal_knowledge_library (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT, name VARCHAR(120), description VARCHAR(500), status VARCHAR(32), created_at TIMESTAMP, updated_at TIMESTAMP)");
        jdbc.execute("CREATE TABLE personal_knowledge_entry (id BIGINT AUTO_INCREMENT PRIMARY KEY, library_id BIGINT, user_id BIGINT, title VARCHAR(255), summary VARCHAR(1000), content_markdown CLOB, source_type VARCHAR(32), source_ref VARCHAR(255), verification_status VARCHAR(32), version INT, created_at TIMESTAMP, updated_at TIMESTAMP)");
        jdbc.execute("CREATE TABLE operator_memory (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT, incident_key VARCHAR(255), memory_type VARCHAR(32), preferred_action TEXT, source_refs TEXT, evidence_count INT, confidence DOUBLE, status VARCHAR(32), created_at TIMESTAMP, updated_at TIMESTAMP)");
        jdbc.update("INSERT INTO vision_event(id,user_id,ocr_status,user_confirmed,ocr_text) VALUES('v1',1,'READY',TRUE,'502 Bad Gateway')");
        jdbc.update("INSERT INTO vision_event(id,user_id,ocr_status,user_confirmed,ocr_text) VALUES('v2',1,'READY',FALSE,'secret')");
        var knowledge = new PersonalKnowledgeService(jdbc);
        service = new VisionHandoffService(jdbc, knowledge, new OperatorMemoryService(jdbc));
    }

    @Test
    void confirmedEventCanBecomePersonalKnowledgeAndMemory() {
        var library = new PersonalKnowledgeService(jdbc).createLibrary(1L, "视觉经验", "");
        var entry = service.toPersonalKnowledge(1L, "v1", library.id(), "502 截图经验");
        assertThat(entry.sourceRef()).isEqualTo("vision:v1");
        assertThat(service.toMemory(1L, "v1", "nginx:502", "先核对 upstream").sourceRefs()).isEqualTo("vision:v1");
    }

    @Test
    void unconfirmedEventCannotBePromoted() {
        var library = new PersonalKnowledgeService(jdbc).createLibrary(1L, "视觉经验", "");
        assertThatThrownBy(() -> service.toPersonalKnowledge(1L, "v2", library.id(), "不应写入"))
                .hasMessage("VISION_EVENT_NOT_CONFIRMED");
    }
}
