package com.smartops.config;

import com.smartops.knowledge.KnowledgePathPolicy;
import com.smartops.knowledge.PersonalKnowledgeStorage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.nio.file.Path;

@Configuration
public class PersonalKnowledgeStorageConfig {
    @Bean
    KnowledgePathPolicy knowledgePathPolicy() { return new KnowledgePathPolicy(); }

    @Bean
    PersonalKnowledgeStorage personalKnowledgeStorage(@Value("${smartops.knowledge.storage-root:data/knowledge}") String root, KnowledgePathPolicy policy) {
        return new PersonalKnowledgeStorage(Path.of(root), policy);
    }
}
