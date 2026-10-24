package com.smartops.assistant;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;

final class BuiltinKnowledgeCatalog {
    private static final int MAX_BYTES = 8 * 1024 * 1024;
    private static final int MAX_ENTRIES = 4096;
    private static final int MAX_CHUNKS = 8192;

    private BuiltinKnowledgeCatalog() {}

    static List<MiniAssistantEngine.Evidence> load() {
        try (var stream = BuiltinKnowledgeCatalog.class.getResourceAsStream("/knowledge/catalog.json")) {
            if (stream == null) throw new IllegalStateException("Built-in knowledge snapshot missing; export catalog before packaging");
            byte[] bytes = stream.readNBytes(MAX_BYTES + 1);
            if (bytes.length > MAX_BYTES) throw new IllegalStateException("Built-in knowledge snapshot exceeds byte limit");
            var root = new ObjectMapper().readTree(bytes);
            var entries = root.path("entries");
            if (root.path("schemaVersion").asInt() != 1 || !entries.isArray()
                    || entries.size() > MAX_ENTRIES || entries.size() != root.path("entryCount").asInt())
                throw new IllegalStateException("Invalid built-in knowledge manifest");
            var identities = new HashSet<String>();
            var result = new ArrayList<MiniAssistantEngine.Evidence>();
            for (var entry : entries) {
                String identity = entry.path("id").asText();
                if (identity.isBlank() || !identities.add(identity) || !"BUILTIN".equals(entry.path("visibility").asText())
                        || !"UNVERIFIED".equals(entry.path("reviewStatus").asText()))
                    throw new IllegalStateException("Invalid built-in knowledge identity or visibility");
                String source = "catalog/" + identity + "@" + entry.path("version").asText() + "#UNVERIFIED";
                String text = entry.path("summary").asText() + "\n" + entry.path("content").asText();
                for (int offset = 0; offset < text.length(); offset += 900) {
                    if (result.size() >= MAX_CHUNKS) throw new IllegalStateException("Built-in knowledge snapshot exceeds chunk limit");
                    int end = Math.min(offset + 1000, text.length());
                    if (end < text.length() && Character.isHighSurrogate(text.charAt(end - 1))) end--;
                    int start = offset > 0 && Character.isLowSurrogate(text.charAt(offset)) ? offset + 1 : offset;
                    result.add(new MiniAssistantEngine.Evidence(identity + ":" + offset, entry.path("title").asText(), source,
                            "内置参考资料，未经人工核验。来源：" + entry.path("source").asText() + "\n" + text.substring(start, end)));
                    if (end == text.length()) break;
                }
            }
            return List.copyOf(result);
        } catch (IOException failure) {
            throw new IllegalStateException("Unable to read built-in knowledge snapshot", failure);
        }
    }
}
