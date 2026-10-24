package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class ArtifactDraftServiceTest {
    private JdbcTemplate jdbc;
    private ArtifactDraftService service;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:artifact-draft-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE artifact_draft (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, artifact_type VARCHAR(32) NOT NULL, title VARCHAR(255) NOT NULL, content LONGTEXT NOT NULL, status VARCHAR(32) NOT NULL, risk VARCHAR(32) NOT NULL, source_ref VARCHAR(255), created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)");
        service = new ArtifactDraftService(jdbc);
    }

    @Test
    void createsDraftAndRequiresValidationBeforeReview() {
        var draft = service.createDraft(1L, "SKILL", "Nginx 502", "# steps\n1. collect evidence", "trace-1", "HIGH");
        assertThat(draft.status()).isEqualTo("DRAFT");
        assertThat(service.submitReview(1L, draft.id()).status()).isEqualTo("PENDING_REVIEW");
    }
}
