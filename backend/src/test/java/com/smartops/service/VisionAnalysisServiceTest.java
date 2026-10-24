package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class VisionAnalysisServiceTest {
    private JdbcTemplate jdbc;
    private VisionAnalysisService service;

    @BeforeEach
    void setUp() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:vision-analysis-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE vision_event (id VARCHAR(36) PRIMARY KEY, user_id BIGINT NOT NULL, ocr_status VARCHAR(32) NOT NULL, analysis_status VARCHAR(32) NOT NULL, privacy_status VARCHAR(32) NOT NULL, user_confirmed BOOLEAN NOT NULL, ocr_text CLOB, confidence DOUBLE, updated_at BIGINT)");
        jdbc.update("INSERT INTO vision_event(id,user_id,ocr_status,analysis_status,privacy_status,user_confirmed) VALUES('v1',1,'QUEUED','NOT_STARTED','UNREVIEWED',FALSE)");
        service = new VisionAnalysisService(jdbc);
    }

    @Test
    void storesLowConfidenceOcrAsManualReviewAndDetectsSecrets() {
        var result = service.recordOcr(1L, "v1", "token=abc123 502 Bad Gateway", 0.61);
        assertThat(result.ocrStatus()).isEqualTo("READY");
        assertThat(result.privacyStatus()).isEqualTo("REDACTION_REQUIRED");
        assertThat(result.analysisStatus()).isEqualTo("MANUAL_REVIEW");
    }
}
