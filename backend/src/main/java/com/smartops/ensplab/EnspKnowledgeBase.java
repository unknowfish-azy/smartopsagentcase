package com.smartops.ensplab;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * eNSP 知识库加载器：把 resources/ensp/kb 下的结构化 JSON 一次性载入内存。
 *
 * <p>教材内容按「项目 → 知识点 / 实验」组织，资源文件是数据的唯一事实来源；
 * 更新教材时只需替换 JSON，不需要改 Java 代码或数据库。</p>
 */
@Component
public class EnspKnowledgeBase {

    private final ObjectMapper mapper = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    private final EnspModels.IndexDoc index;
    private final EnspModels.RulesDoc rules;
    private final EnspModels.ManifestDoc manifest;
    private final Map<String, EnspModels.ModuleDoc> modulesById = new LinkedHashMap<>();
    private final List<EnspModels.ModuleDoc> modules = new ArrayList<>();

    public EnspKnowledgeBase() {
        this.index = read("ensp/kb/index.json", EnspModels.IndexDoc.class);
        this.rules = read("ensp/kb/commands.json", EnspModels.RulesDoc.class);
        this.manifest = read("ensp/topology-manifest.json", EnspModels.ManifestDoc.class);
        for (EnspModels.ModuleEntry entry : index.modules()) {
            String path = "ensp/kb/" + entry.source().substring(entry.source().lastIndexOf('/') + 1);
            EnspModels.ModuleDoc doc = read(path, EnspModels.ModuleDoc.class);
            if (!doc.id().equals(entry.id())) {
                throw new IllegalStateException("KB_MODULE_ID_MISMATCH: " + path);
            }
            modulesById.put(doc.id(), doc);
            modules.add(doc);
        }
    }

    private <T> T read(String classpathLocation, Class<T> type) {
        try (InputStream in = new ClassPathResource(classpathLocation).getInputStream()) {
            return mapper.readValue(in, type);
        } catch (IOException ex) {
            throw new IllegalStateException("ENSPLAB_KB_LOAD_FAILED: " + classpathLocation, ex);
        }
    }

    public InputStream topologyStream(String topologyId) {
        try {
            return new ClassPathResource("ensp/topologies/" + topologyId + ".topo").getInputStream();
        } catch (IOException ex) {
            throw new IllegalArgumentException("TOPOLOGY_NOT_FOUND: " + topologyId, ex);
        }
    }

    public EnspModels.IndexDoc index() {
        return index;
    }

    public EnspModels.RulesDoc rules() {
        return rules;
    }

    public EnspModels.ManifestDoc manifest() {
        return manifest;
    }

    public List<EnspModels.ModuleDoc> modules() {
        return modules;
    }

    public EnspModels.ModuleDoc module(String moduleId) {
        return modulesById.get(moduleId);
    }

    /** 展平所有知识点并附带所属项目，供检索使用。 */
    public List<KnowledgePointHit> knowledgePoints() {
        List<KnowledgePointHit> hits = new ArrayList<>();
        for (EnspModels.ModuleDoc module : modules) {
            for (EnspModels.KnowledgePoint point : module.knowledgePoints()) {
                hits.add(new KnowledgePointHit(module.id(), module.title(), point));
            }
        }
        return hits;
    }

    /** 展平所有实验并附带所属项目标题。 */
    public List<ExperimentHit> experiments() {
        List<ExperimentHit> hits = new ArrayList<>();
        for (EnspModels.ModuleDoc module : modules) {
            for (EnspModels.Experiment experiment : module.experiments()) {
                hits.add(new ExperimentHit(module.id(), module.title(), experiment));
            }
        }
        return hits;
    }

    public record KnowledgePointHit(String moduleId, String moduleTitle,
                                    EnspModels.KnowledgePoint point) {
    }

    public record ExperimentHit(String moduleId, String moduleTitle,
                                EnspModels.Experiment experiment) {
    }
}
