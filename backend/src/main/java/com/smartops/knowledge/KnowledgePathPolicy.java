package com.smartops.knowledge;

import com.smartops.exception.BusinessException;

import java.nio.file.Path;

public final class KnowledgePathPolicy {
    public String slug(String name) {
        if (name == null || name.isBlank()) throw new BusinessException("KNOWLEDGE_LIBRARY_NAME_REQUIRED");
        String value = name.trim().toLowerCase(java.util.Locale.ROOT).replaceAll("[^a-z0-9\\u4e00-\\u9fff]+", "-").replaceAll("^-|-$", "");
        if (value.isBlank()) value = "library";
        return value;
    }

    public Path child(Path root, String relative) {
        if (relative == null || relative.isBlank() || Path.of(relative).isAbsolute()) throw new BusinessException(400, "KNOWLEDGE_PATH_INVALID");
        Path resolved = root.resolve(relative).normalize();
        if (!resolved.startsWith(root.toAbsolutePath().normalize())) throw new BusinessException(400, "KNOWLEDGE_PATH_INVALID");
        return resolved;
    }
}
