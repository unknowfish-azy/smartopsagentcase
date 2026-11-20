package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.CurrentUser;
import com.smartops.service.RiskAssessmentService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 风险评估 REST 端点（P0-3）。
 *
 * <p>提供给前端/Agent 在执行前主动评估风险；
 * 真正的拦截在 OperationToolService.executeInternal 中的风险门，
 * 本端点仅用于预检和审计查询，不构成唯一防线。
 */
@RestController
@RequestMapping("/api/risk")
public class RiskAssessmentController {

    private final RiskAssessmentService riskService;
    private final JdbcTemplate jdbc;

    public RiskAssessmentController(RiskAssessmentService riskService, JdbcTemplate jdbc) {
        this.riskService = riskService;
        this.jdbc = jdbc;
    }

    /** 评估单条命令的风险等级。 */
    @PostMapping("/assess")
    public ApiResponse<?> assess(@CurrentUser Long userId, @RequestBody AssessRequest request) {
        var result = riskService.assess(userId, request.command(), request.toolId(),
                request.context() == null ? Map.of() : request.context());
        return ApiResponse.success(result);
    }

    /** 批量评估多条命令（Agent 输出处置方案时逐条预检）。 */
    @PostMapping("/assess-batch")
    public ApiResponse<?> assessBatch(@CurrentUser Long userId, @RequestBody BatchAssessRequest request) {
        if (request.commands() == null || request.commands().isEmpty()) {
            return ApiResponse.success(List.of());
        }
        var results = request.commands().stream()
                .map(cmd -> riskService.assess(userId, cmd, request.toolId(),
                        request.context() == null ? Map.of() : request.context()))
                .toList();
        return ApiResponse.success(results);
    }

    /** 查询当前用户的风险评估历史。 */
    @GetMapping("/history")
    public ApiResponse<?> history(@CurrentUser Long userId,
                                  @RequestParam(defaultValue = "50") int limit) {
        int capped = Math.max(1, Math.min(200, limit));
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT id,tool_id,command_text,risk_level,risk_score,hit_rules,allowed,created_at " +
                        "FROM risk_assessment_log WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                userId, capped);
        return ApiResponse.success(rows);
    }

    public record AssessRequest(String command, String toolId, Map<String, String> context) {}
    public record BatchAssessRequest(List<String> commands, String toolId, Map<String, String> context) {}
}
