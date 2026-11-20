package com.smartops.guard;

import com.smartops.common.ApiResponse;
import com.smartops.security.CurrentUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * AgentGuard 智测盾 REST 入口。
 *
 * <p>所有读写都按当前登录用户隔离；测评目标只能选择本人已启用的模型连接或内置靶标。</p>
 */
@RestController
@RequestMapping("/api/guard")
public class AgentGuardController {

    private final GuardRunService service;

    public AgentGuardController(GuardRunService service) {
        this.service = service;
    }

    @GetMapping("/overview")
    public ApiResponse<Map<String, Object>> overview(@CurrentUser Long userId) {
        return ApiResponse.success(service.overview(userId));
    }

    @GetMapping("/cases")
    public ApiResponse<List<Map<String, Object>>> cases() {
        return ApiResponse.success(GuardCaseCatalog.view());
    }

    @GetMapping("/targets")
    public ApiResponse<List<Map<String, Object>>> targets(@CurrentUser Long userId) {
        return ApiResponse.success(service.targets(userId));
    }

    @GetMapping("/runs")
    public ApiResponse<List<Map<String, Object>>> runs(
            @CurrentUser Long userId,
            @RequestParam(defaultValue = "30") int limit) {
        return ApiResponse.success(service.listRuns(userId, limit));
    }

    @PostMapping("/runs")
    public ApiResponse<Map<String, Object>> createRun(
            @CurrentUser Long userId,
            @RequestBody GuardRunService.CreateRunCommand command) {
        long runId = service.createRun(userId, command);
        return ApiResponse.success(Map.of("runId", runId));
    }

    @GetMapping("/runs/{id}")
    public ApiResponse<Map<String, Object>> run(@CurrentUser Long userId, @PathVariable long id) {
        return ApiResponse.success(service.runDetail(userId, id));
    }

    @PostMapping("/runs/{id}/baseline")
    public ApiResponse<Map<String, Object>> baseline(@CurrentUser Long userId, @PathVariable long id) {
        return ApiResponse.success(service.markBaseline(userId, id));
    }

    @GetMapping("/runs/{id}/regression")
    public ApiResponse<Map<String, Object>> regression(@CurrentUser Long userId, @PathVariable long id) {
        return ApiResponse.success(service.regression(userId, id));
    }

    @GetMapping("/runs/{id}/export")
    public ApiResponse<Map<String, Object>> export(@CurrentUser Long userId, @PathVariable long id) {
        return ApiResponse.success(service.export(userId, id));
    }
}
