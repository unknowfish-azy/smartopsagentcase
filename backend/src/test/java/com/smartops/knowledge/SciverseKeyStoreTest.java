package com.smartops.knowledge;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SciverseKeyStore 单元测试：upsert 语义与持久化判定。
 * 覆盖 docs/reports/项目知识库热摄入与检索验证-20261117.md §8 中
 * 「手动配置 + 长期保存」的核心不变量：
 *  1. 首次保存 = 追加一行；再次保存 = 原位替换，其余行不动；
 *  2. persisted() 与文件内容一致；
 *  3. 空文件 / 无该变量 / 空值 → 未持久化。
 */
class SciverseKeyStoreTest {

    @TempDir
    Path tempDir;

    private SciverseKeyStore newStore(String fileName) throws IOException {
        Path file = tempDir.resolve(fileName);
        Files.writeString(file, "", StandardCharsets.UTF_8);
        return new SciverseKeyStore(file.toAbsolutePath().toString());
    }

    @Test
    void firstSaveAppendsAndPersists() throws IOException {
        SciverseKeyStore store = newStore(".env.local");
        assertFalse(store.persisted());
        store.save("sci_i_abcdef123456");
        assertEquals("sci_i_abcdef123456", store.readValue());
        assertTrue(store.persisted());
    }

    @Test
    void secondSaveReplacesInPlaceAndKeepsOtherLines() throws IOException {
        Path file = tempDir.resolve(".env.local");
        Files.write(file, List.of(
                "MYSQL_USERNAME=root",
                "SMARTOPS_SCIVERSE_API_KEY=sci_i_old_value_0001",
                "SMARTOPS_LOG_LEVEL=INFO"), StandardCharsets.UTF_8);
        SciverseKeyStore store = new SciverseKeyStore(file.toAbsolutePath().toString());
        assertTrue(store.persisted());

        store.save("sci_i_new_value_0002");
        String content = Files.readString(file, StandardCharsets.UTF_8);
        assertFalse(content.contains("sci_i_old_value_0001"));
        assertTrue(content.contains("SMARTOPS_SCIVERSE_API_KEY=sci_i_new_value_0002"));
        assertTrue(content.contains("MYSQL_USERNAME=root"));
        assertTrue(content.contains("SMARTOPS_LOG_LEVEL=INFO"));
        assertTrue(content.endsWith("\n"));
        assertEquals("sci_i_new_value_0002", store.readValue());
    }

    @Test
    void blankValueOrMissingVariableMeansNotPersisted() throws IOException {
        Path file = tempDir.resolve(".env.local");
        Files.write(file, List.of("MYSQL_USERNAME=root", "SMARTOPS_SCIVERSE_API_KEY="), StandardCharsets.UTF_8);
        SciverseKeyStore store = new SciverseKeyStore(file.toAbsolutePath().toString());
        assertFalse(store.persisted());
        assertNull(store.readValue());
    }

    @Test
    void missingFileMeansNotPersisted() {
        SciverseKeyStore store = new SciverseKeyStore(
                tempDir.resolve("absent.env.local").toAbsolutePath().toString());
        assertFalse(store.persisted());
        assertNull(store.readValue());
    }
}
