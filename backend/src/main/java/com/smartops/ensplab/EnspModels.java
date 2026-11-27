package com.smartops.ensplab;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;

/**
 * eNSP 实验知识库的结构化模型。
 *
 * <p>所有字段直接映射 resources/ensp/kb 下的 JSON，命名与教材目录结构一致，
 * 便于后续用脚本从教材蒸馏结果增量更新而不必改动代码。</p>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public final class EnspModels {

    private EnspModels() {
    }

    /** 知识库索引（kb/index.json）。 */
    public record IndexDoc(String schema, Textbook textbook, List<Category> categories,
                           List<ModuleEntry> modules) {
    }

    public record Textbook(String title, String course, String devicePlatform, String audience) {
    }

    public record Category(String id, String label) {
    }

    public record ModuleEntry(String id, int order, String code, String title,
                              String source, List<String> topologyIds) {
    }

    /** 单个项目（kb/p*.json）。 */
    public record ModuleDoc(String id, int order, String code, String title,
                            List<String> objectives, List<KnowledgePoint> knowledgePoints,
                            List<Experiment> experiments) {
    }

    public record KnowledgePoint(String id, String title, String category, String summary,
                                 String detail, List<String> keyCommands,
                                 List<String> experiments, String acceptance) {
    }

    public record Experiment(String id, String moduleId, String code, String title,
                             String difficulty, Integer durationMin, String topologyId,
                             List<String> goals, List<DeviceRef> devices, List<Step> steps,
                             List<Verify> verification, List<String> commonErrors,
                             List<String> references) {
    }

    public record DeviceRef(String name, String model, String role) {
    }

    public record Step(int seq, String title, String device, String mode, String hint,
                       List<String> commands, String expect) {
    }

    public record Verify(@JsonAlias("cmd") String command, String expect) {
    }

    /** 拓扑清单（topology-manifest.json）。 */
    public record ManifestDoc(List<TopologyMeta> topologies, List<AnswerMeta> answers) {
    }

    public record TopologyMeta(String id, String title, Integer project, String path, String source) {
    }

    public record AnswerMeta(String id, String deviceHint, String path, String source) {
    }

    /** 命令规则库（kb/commands.json）。 */
    public record RulesDoc(List<String> contexts, List<Rule> rules,
                           java.util.Map<String, List<String>> interfacePatterns) {
    }

    public record Rule(String cmd, String match, List<String> contexts, String enter,
                       String desc, String example) {
    }
}
