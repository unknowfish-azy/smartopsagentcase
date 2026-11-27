package com.smartops.ensplab;

import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * eNSP 实验知识库服务层：把知识库 JSON、拓扑解析与命令校验组合成前端可用的视图。
 *
 * <p>所有数据来自 classpath 的 resources/ensp，不依赖数据库；检索在内存中完成，
 * 数据量（8 个模块 / 40 个知识点 / 42 个实验）下延迟可忽略。</p>
 */
@Service
public class EnspLabService {

    private final EnspKnowledgeBase kb;
    private final TopologyParser topologyParser;
    private final ConfigValidator validator;

    public EnspLabService(EnspKnowledgeBase kb, TopologyParser topologyParser, ConfigValidator validator) {
        this.kb = kb;
        this.topologyParser = topologyParser;
        this.validator = validator;
    }

    public OverviewView overview() {
        int points = kb.knowledgePoints().size();
        int experiments = kb.experiments().size();
        int steps = kb.modules().stream()
                .flatMap(m -> m.experiments().stream())
                .mapToInt(e -> e.steps() == null ? 0 : e.steps().size())
                .sum();
        return new OverviewView(kb.index().textbook(), kb.index().categories(),
                new Counts(kb.modules().size(), points, experiments, steps,
                        kb.manifest().topologies().size(), kb.manifest().answers().size()),
                modules());
    }

    public List<ModuleSummaryView> modules() {
        List<ModuleSummaryView> result = new ArrayList<>();
        for (EnspModels.ModuleEntry entry : kb.index().modules()) {
            EnspModels.ModuleDoc doc = kb.module(entry.id());
            int topologyCount = doc == null ? 0
                    : (int) doc.experiments().stream()
                            .map(EnspModels.Experiment::topologyId)
                            .filter(t -> t != null && !t.isBlank())
                            .distinct().count();
            result.add(new ModuleSummaryView(entry, doc == null ? 0 : doc.knowledgePoints().size(),
                    doc == null ? 0 : doc.experiments().size(), topologyCount));
        }
        return result;
    }

    public ModuleDetailView module(String moduleId) {
        EnspModels.ModuleDoc doc = kb.module(moduleId);
        if (doc == null) {
            throw new IllegalArgumentException("MODULE_NOT_FOUND: " + moduleId);
        }
        List<EnspModels.TopologyMeta> topologies = doc.experiments().stream()
                .map(EnspModels.Experiment::topologyId)
                .filter(t -> t != null && !t.isBlank())
                .distinct()
                .map(this::topologyMeta)
                .toList();
        return new ModuleDetailView(doc, topologies, answersOf(doc));
    }

    public List<KnowledgeView> knowledge(String moduleId, String keyword, String category) {
        List<KnowledgeView> result = new ArrayList<>();
        for (EnspKnowledgeBase.KnowledgePointHit hit : kb.knowledgePoints()) {
            if (moduleId != null && !moduleId.isBlank() && !hit.moduleId().equals(moduleId)) {
                continue;
            }
            EnspModels.KnowledgePoint point = hit.point();
            if (category != null && !category.isBlank() && !category.equals(point.category())) {
                continue;
            }
            if (keyword != null && !keyword.isBlank() && !matches(keyword, point.title(), point.summary(),
                    point.detail(), point.keyCommands())) {
                continue;
            }
            result.add(new KnowledgeView(point.id(), hit.moduleId(), point.title(), point.category(),
                    point.summary(), point.keyCommands(), point.experiments(), point.acceptance()));
        }
        return result;
    }

    public List<ExperimentSummaryView> experiments(String moduleId, String keyword, String difficulty) {
        List<ExperimentSummaryView> result = new ArrayList<>();
        for (EnspKnowledgeBase.ExperimentHit hit : kb.experiments()) {
            EnspModels.Experiment experiment = hit.experiment();
            if (moduleId != null && !moduleId.isBlank() && !hit.moduleId().equals(moduleId)) {
                continue;
            }
            if (difficulty != null && !difficulty.isBlank() && !difficulty.equals(experiment.difficulty())) {
                continue;
            }
            if (keyword != null && !keyword.isBlank() && !matches(keyword, experiment.code(), experiment.title(),
                    experiment.goals())) {
                continue;
            }
            result.add(new ExperimentSummaryView(experiment, hit.moduleTitle(), topologyMeta(experiment.topologyId())));
        }
        return result;
    }

    public ExperimentDetailView experiment(String experimentId) {
        EnspKnowledgeBase.ExperimentHit hit = kb.experiments().stream()
                .filter(h -> h.experiment().id().equals(experimentId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("EXPERIMENT_NOT_FOUND: " + experimentId));
        EnspModels.Experiment experiment = hit.experiment();
        TopologyParser.TopologyGraph graph = experiment.topologyId() == null || experiment.topologyId().isBlank()
                ? null
                : topologyParser.parse(experiment.topologyId());
        return new ExperimentDetailView(experiment, hit.moduleTitle(), graph,
                answersOf(List.of(experiment)));
    }

    public List<TopologyListView> topologies() {
        Map<String, Integer> usage = new LinkedHashMap<>();
        for (EnspKnowledgeBase.ExperimentHit hit : kb.experiments()) {
            String topologyId = hit.experiment().topologyId();
            if (topologyId != null && !topologyId.isBlank()) {
                usage.merge(topologyId, 1, Integer::sum);
            }
        }
        List<TopologyListView> result = new ArrayList<>();
        for (EnspModels.TopologyMeta meta : kb.manifest().topologies()) {
            result.add(new TopologyListView(meta, usage.getOrDefault(meta.id(), 0)));
        }
        return result;
    }

    public TopologyParser.TopologyGraph topology(String topologyId) {
        return topologyParser.parse(topologyId);
    }

    public TopologyParser.TopologyGraph parseTopology(String xml, String topologyId) {
        return topologyParser.parseRaw(xml, topologyId);
    }

    public ConfigValidator.ValidationReport validate(List<String> lines, String context) {
        return validator.validate(lines, context == null ? "user" : context);
    }

    public ConfigValidator.ValidationReport validateConfig(String experimentId, List<String> lines) {
        return validator.validateExperiment(experimentId, lines);
    }

    public EnspModels.RulesDoc commands() {
        return kb.rules();
    }

    public StatsView stats() {
        Map<String, ModuleStat> perModule = new LinkedHashMap<>();
        int totalSteps = 0;
        int totalCommands = 0;
        Map<String, Integer> difficulties = new LinkedHashMap<>();
        for (EnspKnowledgeBase.ExperimentHit hit : kb.experiments()) {
            EnspModels.Experiment experiment = hit.experiment();
            totalSteps += experiment.steps() == null ? 0 : experiment.steps().size();
            totalCommands += experiment.steps() == null ? 0
                    : experiment.steps().stream()
                            .mapToInt(s -> s.commands() == null ? 0 : s.commands().size())
                            .sum();
            difficulties.merge(experiment.difficulty(), 1, Integer::sum);
            int stepCount = experiment.steps() == null ? 0 : experiment.steps().size();
            int commandCount = experiment.steps() == null ? 0
                    : experiment.steps().stream()
                            .mapToInt(s -> s.commands() == null ? 0 : s.commands().size())
                            .sum();
            ModuleStat stat = perModule.getOrDefault(hit.moduleId(),
                    new ModuleStat(hit.moduleId(), 0, 0));
            perModule.put(hit.moduleId(), stat.add(stepCount, commandCount));
        }
        return new StatsView(kb.modules().size(), kb.knowledgePoints().size(), kb.experiments().size(),
                totalSteps, totalCommands, kb.manifest().topologies().size(),
                kb.manifest().answers().size(), List.copyOf(perModule.values()), difficulties);
    }

    private EnspModels.TopologyMeta topologyMeta(String topologyId) {
        if (topologyId == null || topologyId.isBlank()) {
            return null;
        }
        return kb.manifest().topologies().stream()
                .filter(t -> t.id().equals(topologyId))
                .findFirst()
                .orElse(null);
    }

    private List<EnspModels.AnswerMeta> answersOf(EnspModels.ModuleDoc doc) {
        return answersOf(doc.experiments().stream().toList());
    }

    private List<EnspModels.AnswerMeta> answersOf(List<EnspModels.Experiment> experiments) {
        List<String> ids = new ArrayList<>();
        for (EnspModels.Experiment experiment : experiments) {
            if (experiment.references() != null) {
                ids.addAll(experiment.references());
            }
        }
        return kb.manifest().answers().stream()
                .filter(a -> ids.contains(a.id()))
                .toList();
    }

    private static boolean matches(String keyword, Object... fields) {
        String needle = keyword.toLowerCase();
        for (Object field : fields) {
            if (field == null) {
                continue;
            }
            if (field instanceof String text) {
                if (text.toLowerCase().contains(needle)) {
                    return true;
                }
            } else if (field instanceof Iterable<?> items) {
                for (Object item : items) {
                    if (item != null && item.toString().toLowerCase().contains(needle)) {
                        return true;
                    }
                }
            }
        }
        return false;
    }

    public record Counts(int modules, int knowledgePoints, int experiments, int steps,
                         int topologies, int answers) {
    }

    public record OverviewView(EnspModels.Textbook textbook, List<EnspModels.Category> categories,
                               Counts counts, List<ModuleSummaryView> modules) {
    }

    public record ModuleSummaryView(EnspModels.ModuleEntry module, int knowledgePoints,
                                    int experiments, int topologies) {
    }

    public record ModuleDetailView(EnspModels.ModuleDoc module, List<EnspModels.TopologyMeta> topologies,
                                  List<EnspModels.AnswerMeta> answers) {
    }

    public record KnowledgeView(String id, String moduleId, String title, String category,
                                String summary, List<String> keyCommands,
                                List<String> experiments, String acceptance) {
    }

    public record ExperimentSummaryView(EnspModels.Experiment experiment, String moduleTitle,
                                        EnspModels.TopologyMeta topology) {
    }

    public record ExperimentDetailView(EnspModels.Experiment experiment, String moduleTitle,
                                       TopologyParser.TopologyGraph topology,
                                       List<EnspModels.AnswerMeta> answers) {
    }

    public record TopologyListView(EnspModels.TopologyMeta topology, int experimentCount) {
    }

    public record ModuleStat(String moduleId, int steps, int commands) {
        private ModuleStat add(int stepDelta, int commandDelta) {
            return new ModuleStat(moduleId, steps + stepDelta, commands + commandDelta);
        }
    }

    public record StatsView(int modules, int knowledgePoints, int experiments, int steps,
                            int commands, int topologies, int answers,
                            List<ModuleStat> perModule, Map<String, Integer> difficulties) {
    }
}
