package com.smartops.knowledge;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class PersonalKnowledgeStorageTest {
    @TempDir Path tempDir;

    @Test
    void resolvesOnlyInsideUserRootAndWritesUtf8Atomically() throws Exception {
        var storage = new PersonalKnowledgeStorage(tempDir, new KnowledgePathPolicy());
        var location = storage.createUserLibrary(7L, "生产故障");
        storage.writeEntryAtomically(location, "nginx-502.md", "# 502\n".getBytes(StandardCharsets.UTF_8));
        assertEquals("# 502\n", Files.readString(location.entries().resolve("nginx-502.md")));
        assertThrows(RuntimeException.class, () -> storage.resolveEntry(7L, location.slug(), "../other.md"));
    }

    @Test
    void createsExpectedLibraryLayoutAndHash() throws Exception {
        var storage = new PersonalKnowledgeStorage(tempDir, new KnowledgePathPolicy());
        var location = storage.createUserLibrary(8L, "网络");
        assertTrue(Files.isDirectory(location.root()));
        assertTrue(Files.exists(location.root().resolve("library.json")));
        assertTrue(Files.exists(location.root().resolve("index.json")));
        assertTrue(Files.exists(location.root().resolve("README.md")));
        assertEquals(64, storage.sha256("hello".getBytes(StandardCharsets.UTF_8)).length());
    }
}
