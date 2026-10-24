package com.smartops.knowledge;

import com.smartops.exception.BusinessException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.UUID;

public final class PersonalKnowledgeStorage {
    private final Path root;
    private final KnowledgePathPolicy paths;

    public PersonalKnowledgeStorage(Path root, KnowledgePathPolicy paths) {
        this.root = root.toAbsolutePath().normalize();
        this.paths = paths;
    }

    public StorageLocation createUserLibrary(long userId, String name) throws IOException {
        String slug = paths.slug(name) + "-" + UUID.randomUUID().toString().substring(0, 8);
        Path userRoot = userRoot(userId);
        Path libraryRoot = paths.child(userRoot, "libraries/" + slug);
        Files.createDirectories(libraryRoot.resolve("entries"));
        Files.createDirectories(libraryRoot.resolve("attachments"));
        Files.createDirectories(userRoot.resolve("inbox"));
        Files.createDirectories(userRoot.resolve("exports"));
        Files.createDirectories(userRoot.resolve("trash"));
        Files.writeString(libraryRoot.resolve("library.json"), "{\"name\":\"" + escape(name) + "\"}\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        Files.writeString(libraryRoot.resolve("index.json"), "{\"version\":1,\"entries\":[]}\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        Files.writeString(libraryRoot.resolve("README.md"), "# " + name.trim() + "\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        return new StorageLocation(userRoot, libraryRoot, libraryRoot.resolve("entries"), libraryRoot.resolve("attachments"), slug);
    }

    public Path resolveEntry(long userId, String slug, String relative) {
        Path library = paths.child(userRoot(userId), "libraries/" + slug);
        return paths.child(library.resolve("entries").toAbsolutePath().normalize(), relative);
    }

    public Path writeEntryAtomically(StorageLocation location, String relative, byte[] content) throws IOException {
        Path target = paths.child(location.entries(), relative);
        Files.createDirectories(target.getParent());
        Path temporary = target.resolveSibling(target.getFileName() + "." + UUID.randomUUID() + ".tmp");
        try {
            Files.write(temporary, content, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            try { Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
            catch (AtomicMoveNotSupportedException e) { Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING); }
            return target;
        } finally { Files.deleteIfExists(temporary); }
    }

    public Path writeEntryAtomically(long userId, String slug, String relative, byte[] content) throws IOException {
        Path library = paths.child(userRoot(userId), "libraries/" + slug);
        Path entries = paths.child(library, "entries");
        return writeEntryAtomically(new StorageLocation(userRoot(userId), library, entries, paths.child(library, "attachments"), slug), relative, content);
    }

    public byte[] readEntry(long userId, String slug, String relative) throws IOException {
        return Files.readAllBytes(resolveEntry(userId, slug, relative));
    }

    public void moveLibraryToTrash(long userId, String slug) throws IOException {
        Path source = paths.child(userRoot(userId), "libraries/" + slug);
        Path trash = paths.child(userRoot(userId), "trash/" + slug + "-" + System.currentTimeMillis());
        Files.createDirectories(trash.getParent());
        if (Files.exists(source)) Files.move(source, trash, StandardCopyOption.REPLACE_EXISTING);
    }

    public void restoreLibraryFromTrash(long userId, String slug) throws IOException {
        Path libraries = paths.child(userRoot(userId), "libraries");
        Path trash = paths.child(userRoot(userId), "trash");
        try (var stream = Files.list(trash)) {
            Path candidate = stream.filter(Files::isDirectory).filter(path -> path.getFileName().toString().startsWith(slug + "-")).max(java.util.Comparator.comparing(Path::toString)).orElse(null);
            if (candidate != null) Files.move(candidate, libraries.resolve(slug), StandardCopyOption.REPLACE_EXISTING);
        }
    }

    public String sha256(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (Exception e) { throw new IllegalStateException("SHA-256 unavailable", e); }
    }

    private Path userRoot(long userId) {
        if (userId <= 0) throw new BusinessException(400, "KNOWLEDGE_USER_INVALID");
        return paths.child(root, "users/" + userId);
    }

    private static String escape(String value) { return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n"); }

    public record StorageLocation(Path userRoot, Path root, Path entries, Path attachments, String slug) {}
}
