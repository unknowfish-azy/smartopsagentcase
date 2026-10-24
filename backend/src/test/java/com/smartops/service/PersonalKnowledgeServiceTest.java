package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PersonalKnowledgeServiceTest {
    private JdbcTemplate jdbc;
    private PersonalKnowledgeService service;

    @BeforeEach
    void setUp() {
        var dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:personal-knowledge-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE personal_knowledge_library (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, name VARCHAR(120) NOT NULL, description VARCHAR(500), status VARCHAR(32) NOT NULL, storage_slug VARCHAR(160), storage_status VARCHAR(32), created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE personal_knowledge_entry (id BIGINT AUTO_INCREMENT PRIMARY KEY, library_id BIGINT NOT NULL, user_id BIGINT NOT NULL, title VARCHAR(255) NOT NULL, summary VARCHAR(1000) NOT NULL, content_markdown CLOB NOT NULL, source_type VARCHAR(32) NOT NULL, source_ref VARCHAR(255), entry_relative_path VARCHAR(512), content_hash VARCHAR(64), index_status VARCHAR(32), index_error VARCHAR(1000), verification_status VARCHAR(32) NOT NULL, version INT NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)");
        service = new PersonalKnowledgeService(jdbc);
    }

    @Test
    void createsAndListsOnlyEntriesOwnedByCurrentUser() {
        var library = service.createLibrary(1L, "我的排障经验", "个人确认过的处理路径");
        service.createEntry(1L, library.id(), "Nginx 502", "上游超时", "# 只读排查", "INCIDENT", "trace-1");
        var otherLibrary = service.createLibrary(2L, "他人的资料", "private");
        service.createEntry(2L, otherLibrary.id(), "Private", "hidden", "secret", "MANUAL", null);

        var page = service.listEntries(1L, library.id(), null, 1, 20);

        assertThat(page.total()).isEqualTo(1);
        assertThat(page.items()).extracting(PersonalKnowledgeService.Entry::title).containsExactly("Nginx 502");
    }

    @Test
    void rejectsCrossUserLibraryAccessAndSupportsArchiveDelete() {
        var library = service.createLibrary(1L, "我的资料", "");

        assertThatThrownBy(() -> service.createEntry(2L, library.id(), "越权", "", "x", "MANUAL", null))
                .isInstanceOf(BusinessException.class)
                .hasMessage("KNOWLEDGE_LIBRARY_NOT_FOUND");

        var entry = service.createEntry(1L, library.id(), "可归档", "", "x", "MANUAL", null);
        service.archiveEntry(1L, entry.id());
        assertThat(service.detailEntry(1L, entry.id()).verificationStatus()).isEqualTo("ARCHIVED");
        service.deleteEntry(1L, entry.id());
        assertThatThrownBy(() -> service.detailEntry(1L, entry.id()))
                .isInstanceOf(BusinessException.class)
                .hasMessage("KNOWLEDGE_ENTRY_NOT_FOUND");
    }
}
