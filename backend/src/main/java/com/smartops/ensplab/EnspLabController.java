package com.smartops.ensplab;

import com.smartops.common.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * eNSP 实验知识库接口（华为《网络设备安装与调试（eNSP 模拟器）》第二版）。
 *
 * <p>只读目录 + 本地校验：知识点、实验、拓扑、命令规则全部来自 classpath 资源，
 * 不在服务端保存用户数据。前端拿到实验步骤与期望命令后自行引导，配置校验在这里完成，
 * 保证「教材标准」只有一份来源（resources/ensp/kb）。</p>
 */
@RestController
@RequestMapping("/api/ensp")
@RequiredArgsConstructor
public class EnspLabController {

    private final EnspLabService service;

    /** 教材总览：课程信息 + 分类 + 数量统计 + 模块卡片。 */
    @GetMapping("/overview")
    public ApiResponse<EnspLabService.OverviewView> overview() {
        return ApiResponse.success(service.overview());
    }

    /** 项目（模块）卡片列表。 */
    @GetMapping("/modules")
    public ApiResponse<List<EnspLabService.ModuleSummaryView>> modules() {
        return ApiResponse.success(service.modules());
    }

    /** 单个项目的知识点树与关联拓扑 / 答案清单。 */
    @GetMapping("/modules/{id}")
    public ApiResponse<EnspLabService.ModuleDetailView> module(@PathVariable String id) {
        return ApiResponse.success(service.module(id));
    }

    /** 知识点检索：可按项目、分类与关键词过滤。 */
    @GetMapping("/knowledge")
    public ApiResponse<List<EnspLabService.KnowledgeView>> knowledge(
            @RequestParam(required = false) String moduleId,
            @RequestParam(required = false) String category,
            @RequestParam(required = false) String keyword) {
        return ApiResponse.success(service.knowledge(moduleId, keyword, category));
    }

    /** 实验列表：可按项目、难度与关键词过滤。 */
    @GetMapping("/experiments")
    public ApiResponse<List<EnspLabService.ExperimentSummaryView>> experiments(
            @RequestParam(required = false) String moduleId,
            @RequestParam(required = false) String difficulty,
            @RequestParam(required = false) String keyword) {
        return ApiResponse.success(service.experiments(moduleId, keyword, difficulty));
    }

    /** 实验详情：步骤、验证命令、关联拓扑图与参考答案清单。 */
    @GetMapping("/experiments/{id}")
    public ApiResponse<EnspLabService.ExperimentDetailView> experiment(@PathVariable String id) {
        return ApiResponse.success(service.experiment(id));
    }

    /** 拓扑资产清单（含被实验引用次数）。 */
    @GetMapping("/topologies")
    public ApiResponse<List<EnspLabService.TopologyListView>> topologies() {
        return ApiResponse.success(service.topologies());
    }

    /** 解析后的拓扑图：设备节点、端口连线、画布文本标注。 */
    @GetMapping("/topologies/{id}")
    public ApiResponse<TopologyParser.TopologyGraph> topology(@PathVariable String id) {
        return ApiResponse.success(service.topology(id));
    }

    /** 命令规则库（视图定义、正则、进入视图），供前端做命令提示。 */
    @GetMapping("/commands")
    public ApiResponse<EnspModels.RulesDoc> commands() {
        return ApiResponse.success(service.commands());
    }

    /** 知识库统计：规模、难度分布、各模块步骤与命令数。 */
    @GetMapping("/stats")
    public ApiResponse<EnspLabService.StatsView> stats() {
        return ApiResponse.success(service.stats());
    }

    /** 粘贴 / 上传 .topo XML，返回可渲染的拓扑图。 */
    @PostMapping("/topologies/parse")
    public ApiResponse<TopologyParser.TopologyGraph> parseTopology(@Valid @RequestBody TopologyParseInput input) {
        return ApiResponse.success(service.parseTopology(input.xml(), input.topologyId()));
    }

    /** 逐行校验一段配置（可带提示符与回显），返回每行状态与最终视图。 */
    @PostMapping("/validate")
    public ApiResponse<ConfigValidator.ValidationReport> validate(@Valid @RequestBody ValidateInput input) {
        return ApiResponse.success(service.validate(input.lines(), input.context()));
    }

    /** 与指定实验的期望命令比对，返回得分、缺失命令与分步进度。 */
    @PostMapping("/validate-config")
    public ApiResponse<ConfigValidator.ValidationReport> validateConfig(@Valid @RequestBody ValidateConfigInput input) {
        return ApiResponse.success(service.validateConfig(input.experimentId(), input.lines()));
    }

    public record TopologyParseInput(
            @NotBlank(message = "ENSPLAB_XML_REQUIRED: 缺少拓扑 XML") String xml,
            String topologyId) {
    }

    public record ValidateInput(List<String> lines, String context) {
    }

    public record ValidateConfigInput(
            @NotBlank(message = "ENSPLAB_EXPERIMENT_ID_REQUIRED: 缺少实验 id") String experimentId,
            List<String> lines) {
    }
}
