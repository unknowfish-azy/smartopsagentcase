package com.smartops.knowledge;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

@Service
public class PersonalKnowledgeIndexService {
    private final JdbcTemplate jdbc;
    private final PersonalKnowledgeStorage storage;

    public PersonalKnowledgeIndexService(JdbcTemplate jdbc, PersonalKnowledgeStorage storage) { this.jdbc = jdbc; this.storage = storage; }

    public HealthReport rebuild(Long userId, Long libraryId) {
        var rows = jdbc.query("SELECT id,entry_relative_path FROM personal_knowledge_entry WHERE user_id=? AND library_id=? AND verification_status NOT IN ('DRAFT','REJECTED','ARCHIVED')", (rs, row) -> new EntryPath(rs.getLong("id"), rs.getString("entry_relative_path")), userId, libraryId);
        int ready = 0;
        List<String> missing = new ArrayList<>();
        for (var entry : rows) {
            if (entry.path() == null || entry.path().isBlank()) continue;
            try {
                Path file = storage.resolveEntry(userId, librarySlug(libraryId, userId), entry.path());
                byte[] content = Files.readAllBytes(file);
                jdbc.update("UPDATE personal_knowledge_entry SET content_hash=?,index_status='READY',index_error=NULL WHERE id=? AND user_id=?", storage.sha256(content), entry.id(), userId);
                ready++;
            } catch (IOException | RuntimeException failure) {
                jdbc.update("UPDATE personal_knowledge_entry SET index_status='MISSING_FILE',index_error=? WHERE id=? AND user_id=?", failure.getMessage(), entry.id(), userId);
                missing.add(entry.path());
            }
        }
        return new HealthReport(ready, missing);
    }

    private String librarySlug(Long libraryId, Long userId) { return jdbc.queryForObject("SELECT storage_slug FROM personal_knowledge_library WHERE id=? AND user_id=?", String.class, libraryId, userId); }
    private record EntryPath(Long id, String path) {}
    public record HealthReport(int ready, List<String> missing) {}
}
