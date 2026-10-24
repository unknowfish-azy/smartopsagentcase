package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class VisionEventServiceTest {
    private JdbcTemplate jdbc;
    private VisionEventService service;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:vision-event-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE chat_conversation (id VARCHAR(36) PRIMARY KEY, owner_id BIGINT NOT NULL, team_id BIGINT, scope_key VARCHAR(80) NOT NULL)");
        jdbc.execute("CREATE TABLE chat_attachment (id VARCHAR(36) PRIMARY KEY, conversation_id VARCHAR(36) NOT NULL, message_id VARCHAR(36), name VARCHAR(255) NOT NULL, media_type VARCHAR(128) NOT NULL, byte_size BIGINT NOT NULL)");
        jdbc.execute("CREATE TABLE vision_event (id VARCHAR(36) PRIMARY KEY, conversation_id VARCHAR(36) NOT NULL, attachment_id VARCHAR(36) NOT NULL, user_id BIGINT NOT NULL, source_type VARCHAR(32) NOT NULL, ocr_status VARCHAR(32) NOT NULL, analysis_status VARCHAR(32) NOT NULL, privacy_status VARCHAR(32) NOT NULL, user_confirmed BOOLEAN NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, UNIQUE(attachment_id))");
        jdbc.update("INSERT INTO chat_conversation(id,owner_id,scope_key) VALUES('c1',1,'user:1'),('c2',2,'user:2')");
        jdbc.update("INSERT INTO chat_attachment(id,conversation_id,message_id,name,media_type,byte_size) VALUES('a1','c1','m1','screen.png','image/png',100),('a2','c2','m2','other.png','image/png',100)");
        service = new VisionEventService(jdbc);
    }

    @Test
    void createsQueuedEventForOwnedBoundImageAndTransitionsToReady() {
        var event = service.create(1L, "c1", "a1", "SCREENSHOT");
        assertThat(event.ocrStatus()).isEqualTo("QUEUED");
        assertThat(service.markReady(1L, event.id()).ocrStatus()).isEqualTo("READY");
    }

    @Test
    void hidesAnotherUsersAttachmentAndRejectsNonImage() {
        assertThatThrownBy(() -> service.create(1L, "c2", "a2", "FILE")).hasMessage("VISION_ATTACHMENT_NOT_FOUND");
    }
}
