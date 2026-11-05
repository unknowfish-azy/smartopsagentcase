package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.knowledge.PersonalKnowledgeStorage;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.beans.factory.annotation.Autowired;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

@Service
public class PersonalKnowledgeService {
    private final JdbcTemplate jdbc;
    private final PersonalKnowledgeStorage storage;

    public PersonalKnowledgeService(JdbcTemplate jdbc) { this(jdbc, null); }
    @Autowired
    public PersonalKnowledgeService(JdbcTemplate jdbc, PersonalKnowledgeStorage storage) { this.jdbc = jdbc; this.storage = storage; }

    @Transactional
    public Library createLibrary(Long userId, String name, String description) {
        requireText(name, "KNOWLEDGE_LIBRARY_NAME_REQUIRED");
        Instant now = Instant.now();
        PersonalKnowledgeStorage.StorageLocation location = null;
        try {
            if (storage != null) location = storage.createUserLibrary(userId, name);
            if (storage == null) {
                jdbc.update("INSERT INTO personal_knowledge_library(user_id,name,description,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                        userId, name.trim(), safe(description), "ACTIVE", Timestamp.from(now), Timestamp.from(now));
            } else {
                jdbc.update("INSERT INTO personal_knowledge_library(user_id,name,description,status,storage_slug,storage_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        userId, name.trim(), safe(description), "ACTIVE", location.slug(), "ACTIVE", Timestamp.from(now), Timestamp.from(now));
            }
        } catch (Exception failure) {
            throw new BusinessException(500, "KNOWLEDGE_STORAGE_CREATE_FAILED");
        }
        Long id = jdbc.queryForObject("SELECT MAX(id) FROM personal_knowledge_library WHERE user_id=?", Long.class, userId);
        return detailLibrary(userId, id);
    }

    public Library detailLibrary(Long userId, Long libraryId) {
        String select = storage == null
                ? "SELECT id,user_id,name,description,status,created_at,updated_at FROM personal_knowledge_library WHERE id=? AND user_id=?"
                : "SELECT id,user_id,name,description,status,storage_slug,storage_status,created_at,updated_at FROM personal_knowledge_library WHERE id=? AND user_id=?";
        List<Library> rows = jdbc.query(select,
                (rs, row) -> new Library(rs.getLong("id"), rs.getLong("user_id"), rs.getString("name"), rs.getString("description"), rs.getString("status"), storage == null ? null : rs.getString("storage_slug"), storage == null ? "LEGACY" : rs.getString("storage_status"), rs.getTimestamp("created_at").toInstant(), rs.getTimestamp("updated_at").toInstant()), libraryId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "KNOWLEDGE_LIBRARY_NOT_FOUND");
        return rows.get(0);
    }

    public List<Library> listLibraries(Long userId) {
        String select = storage == null
                ? "SELECT id,user_id,name,description,status,created_at,updated_at FROM personal_knowledge_library WHERE user_id=? ORDER BY updated_at DESC,id DESC"
                : "SELECT id,user_id,name,description,status,storage_slug,storage_status,created_at,updated_at FROM personal_knowledge_library WHERE user_id=? ORDER BY updated_at DESC,id DESC";
        return jdbc.query(select,
                (rs, row) -> new Library(rs.getLong("id"), rs.getLong("user_id"), rs.getString("name"), rs.getString("description"), rs.getString("status"), storage == null ? null : rs.getString("storage_slug"), storage == null ? "LEGACY" : rs.getString("storage_status"), rs.getTimestamp("created_at").toInstant(), rs.getTimestamp("updated_at").toInstant()), userId);
    }

    @Transactional
    public Library renameLibrary(Long userId, Long libraryId, String name, String description) {
        detailLibrary(userId, libraryId);
        requireText(name, "KNOWLEDGE_LIBRARY_NAME_REQUIRED");
        jdbc.update("UPDATE personal_knowledge_library SET name=?,description=?,updated_at=? WHERE id=? AND user_id=?", name.trim(), safe(description), Timestamp.from(Instant.now()), libraryId, userId);
        return detailLibrary(userId, libraryId);
    }

    @Transactional
    public Library setLibraryStatus(Long userId, Long libraryId, String status) {
        var current = detailLibrary(userId, libraryId);
        if (!List.of("ACTIVE", "ARCHIVED").contains(status)) throw new BusinessException(400, "KNOWLEDGE_LIBRARY_STATUS_INVALID");
        jdbc.update("UPDATE personal_knowledge_library SET status=?,storage_status=?,updated_at=? WHERE id=? AND user_id=?", status, status, Timestamp.from(Instant.now()), libraryId, userId);
        if (storage != null && current.storageSlug() != null) {
            try {
                if ("ARCHIVED".equals(status)) storage.moveLibraryToTrash(userId, current.storageSlug());
                else storage.restoreLibraryFromTrash(userId, current.storageSlug());
            } catch (Exception e) { throw new BusinessException(500, "KNOWLEDGE_STORAGE_STATUS_FAILED"); }
        }
        return detailLibrary(userId, libraryId);
    }

    @Transactional
    public Entry createEntry(Long userId, Long libraryId, String title, String summary, String markdown, String sourceType, String sourceRef) {
        detailLibrary(userId, libraryId);
        requireText(title, "KNOWLEDGE_ENTRY_TITLE_REQUIRED");
        requireText(markdown, "KNOWLEDGE_ENTRY_CONTENT_REQUIRED");
        Instant now = Instant.now();
        String relativePath = title.trim().replaceAll("[^a-zA-Z0-9\\u4e00-\\u9fff]+", "-").replaceAll("^-|-$", "") + ".md";
        var library = detailLibrary(userId, libraryId);
        try {
            if (storage != null && library.storageSlug() != null) {
                storage.writeEntryAtomically(userId, library.storageSlug(), relativePath, markdown.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            }
            if (storage == null) {
                jdbc.update("INSERT INTO personal_knowledge_entry(library_id,user_id,title,summary,content_markdown,source_type,source_ref,verification_status,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        libraryId, userId, title.trim(), safe(summary), markdown, safe(sourceType).isBlank() ? "MANUAL" : sourceType.trim(), sourceRef, "UNVERIFIED", 1, Timestamp.from(now), Timestamp.from(now));
            } else {
                jdbc.update("INSERT INTO personal_knowledge_entry(library_id,user_id,title,summary,content_markdown,source_type,source_ref,entry_relative_path,content_hash,index_status,verification_status,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        libraryId, userId, title.trim(), safe(summary), markdown, safe(sourceType).isBlank() ? "MANUAL" : sourceType.trim(), sourceRef, relativePath, storage.sha256(markdown.getBytes(java.nio.charset.StandardCharsets.UTF_8)), "READY", "UNVERIFIED", 1, Timestamp.from(now), Timestamp.from(now));
            }
        } catch (Exception failure) { throw new BusinessException(500, "KNOWLEDGE_ENTRY_STORAGE_FAILED"); }
        Long id = jdbc.queryForObject("SELECT MAX(id) FROM personal_knowledge_entry WHERE user_id=? AND library_id=?", Long.class, userId, libraryId);
        return detailEntry(userId, id);
    }

    public EntryPage listEntries(Long userId, Long libraryId, String query, int page, int pageSize) {
        detailLibrary(userId, libraryId);
        int safePage = Math.max(1, page);
        int safeSize = Math.max(1, Math.min(100, pageSize));
        boolean filtered = query != null && !query.isBlank();
        String where = filtered ? " WHERE user_id=? AND library_id=? AND (LOWER(title) LIKE ? OR LOWER(summary) LIKE ? OR LOWER(CAST(content_markdown AS VARCHAR(2000))) LIKE ?)" : " WHERE user_id=? AND library_id=?";
        String value = filtered ? "%" + query.trim().toLowerCase() + "%" : null;
        Object[] countArgs = filtered ? new Object[]{userId, libraryId, value, value, value} : new Object[]{userId, libraryId};
        long total = jdbc.queryForObject("SELECT COUNT(*) FROM personal_knowledge_entry" + where, Long.class, countArgs);
        Object[] args = filtered ? new Object[]{userId, libraryId, value, value, value, safeSize, (safePage - 1) * safeSize} : new Object[]{userId, libraryId, safeSize, (safePage - 1) * safeSize};
        List<Entry> items = jdbc.query("SELECT id,library_id,user_id,title,summary,content_markdown,source_type,source_ref,verification_status,version,created_at,updated_at FROM personal_knowledge_entry" + where + " ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?", this::mapEntry, args);
        return new EntryPage(items, total, safePage, safeSize);
    }

    public Entry detailEntry(Long userId, Long entryId) {
        List<Entry> rows = jdbc.query("SELECT id,library_id,user_id,title,summary,content_markdown,source_type,source_ref,verification_status,version,created_at,updated_at FROM personal_knowledge_entry WHERE id=? AND user_id=?", this::mapEntry, entryId, userId);
        if (rows.isEmpty()) throw new BusinessException(404, "KNOWLEDGE_ENTRY_NOT_FOUND");
        return rows.get(0);
    }

    @Transactional
    public void archiveEntry(Long userId, Long entryId) {
        detailEntry(userId, entryId);
        jdbc.update("UPDATE personal_knowledge_entry SET verification_status='ARCHIVED',updated_at=? WHERE id=? AND user_id=?", Timestamp.from(Instant.now()), entryId, userId);
    }

    @Transactional
    public void deleteEntry(Long userId, Long entryId) {
        detailEntry(userId, entryId);
        jdbc.update("DELETE FROM personal_knowledge_entry WHERE id=? AND user_id=?", entryId, userId);
    }

    @Transactional
    public Entry updateEntry(Long userId, Long entryId, String title, String summary, String markdown) {
        Entry current = detailEntry(userId, entryId);
        requireText(title, "KNOWLEDGE_ENTRY_TITLE_REQUIRED");
        requireText(markdown, "KNOWLEDGE_ENTRY_CONTENT_REQUIRED");
        jdbc.update("UPDATE personal_knowledge_entry SET title=?,summary=?,content_markdown=?,content_hash=?,index_status='READY',version=version+1,updated_at=? WHERE id=? AND user_id=?",
                title.trim(), safe(summary), markdown, storage == null ? null : storage.sha256(markdown.getBytes(java.nio.charset.StandardCharsets.UTF_8)), Timestamp.from(Instant.now()), entryId, userId);
        return detailEntry(userId, current.id());
    }

    private Entry mapEntry(java.sql.ResultSet rs, int row) throws java.sql.SQLException {
        return new Entry(rs.getLong("id"), rs.getLong("library_id"), rs.getLong("user_id"), rs.getString("title"), rs.getString("summary"), rs.getString("content_markdown"), rs.getString("source_type"), rs.getString("source_ref"), rs.getString("verification_status"), rs.getInt("version"), rs.getTimestamp("created_at").toInstant(), rs.getTimestamp("updated_at").toInstant());
    }

    private static void requireText(String value, String code) { if (value == null || value.isBlank()) throw new BusinessException(code); }
    private static String safe(String value) { return value == null ? "" : value; }

    public record Library(Long id, Long userId, String name, String description, String status, String storageSlug, String storageStatus, Instant createdAt, Instant updatedAt) {}
    public record Entry(Long id, Long libraryId, Long userId, String title, String summary, String contentMarkdown, String sourceType, String sourceRef, String verificationStatus, int version, Instant createdAt, Instant updatedAt) {}
    public record EntryPage(List<Entry> items, long total, int page, int pageSize) {}
}
