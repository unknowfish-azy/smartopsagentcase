package com.smartops.assistant;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import static org.assertj.core.api.Assertions.*;

class BuiltinKnowledgeCatalogTest {
    @TempDir Path temporary;

    @Test void includes_canonical_catalog_when_local_markdown_directory_is_missing() {
        var index = new LocalKnowledgeIndex(temporary.resolve("missing"), true);
        var result = index.search("ImagePullBackOff");
        assertThat(result).isNotEmpty();
        assertThat(result).anySatisfy(evidence -> {
            assertThat(evidence.source()).startsWith("catalog/");
            assertThat(evidence.source()).contains("@", "UNVERIFIED");
            assertThat(evidence.snippet()).containsIgnoringCase("ImagePullBackOff");
        });
    }

    @Test void fixture_index_can_exclude_builtin_sources_explicitly() {
        assertThat(new LocalKnowledgeIndex(temporary, false).search("ImagePullBackOff")).isEmpty();
    }
}
