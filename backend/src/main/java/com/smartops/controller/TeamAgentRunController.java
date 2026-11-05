package com.smartops.controller;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.common.ApiResponse;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.service.OperationToolService;
import com.smartops.service.TeamAgentRunService;
import com.smartops.operations.OperationRuntimeRegistry;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

@RestController
public class TeamAgentRunController {
    private final TeamAgentRunService runs;
    private final OperationToolService operations;
    private final ObjectMapper mapper;
    private final OperationRuntimeRegistry runtimes;

    public TeamAgentRunController(TeamAgentRunService runs, OperationToolService operations, ObjectMapper mapper,
                                  OperationRuntimeRegistry runtimes) {
        this.runs = runs; this.operations = operations; this.mapper = mapper; this.runtimes = runtimes;
    }

    @PostMapping("/api/teams/{teamId}/agents/{agentId}/runs")
    public ApiResponse<?> create(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId, @PathVariable long agentId,
                                 @Valid @RequestBody CreateInput input) {
        runtimes.requireOwned(input.runtimeId(), actor.id());
        return ApiResponse.success(runs.create(actor, teamId, agentId, input.versionId(), input.runtimeId(), input.toolId(), input.parameters()));
    }

    @GetMapping("/api/team-agent-runs/{runId}")
    public ApiResponse<?> detail(@AuthenticationPrincipal SessionUser actor, @PathVariable long runId) {
        return ApiResponse.success(runs.require(actor, runId));
    }

    @GetMapping("/api/teams/{teamId}/runs")
    public ApiResponse<?> list(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId) {
        return ApiResponse.success(runs.list(actor, teamId));
    }

    @GetMapping("/api/teams/{teamId}/approvals")
    public ApiResponse<?> pendingApprovals(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId) {
        return ApiResponse.success(runs.pendingApprovals(actor, teamId));
    }

    /**
     * 审批。可选带决策依据（协作优化 1）：只写 `approved_by` 只能回答"谁批的"，
     * 带上依据才能回答"基于什么批的"。
     *
     * <p>依据是可选的：强制填写会让人写"ok"绕过，反而失去信息量。
     * 请求体可省略，以兼容既有前端调用。</p>
     */
    @PostMapping("/api/team-agent-runs/{runId}/approve")
    public ApiResponse<?> approve(@AuthenticationPrincipal SessionUser actor, @PathVariable long runId,
                                  @RequestBody(required = false) ApproveRequest request) {
        return ApiResponse.success(runs.approve(actor, runId, request == null ? null : request.decisionBasis()));
    }

    public record ApproveRequest(String decisionBasis) {}

    @PostMapping("/api/team-agent-runs/{runId}/preview")
    public ApiResponse<?> preview(@AuthenticationPrincipal SessionUser actor, @PathVariable long runId) {
        var run = runs.requireReviewer(actor, runId);
        if (!"PENDING_APPROVAL".equals(run.status())) throw new BusinessException(409, "TEAM_RUN_NOT_PENDING");
        Map<String, String> parameters;
        try { parameters = mapper.readValue(run.parametersJson(), new TypeReference<>() {}); }
        catch (com.fasterxml.jackson.core.JsonProcessingException invalid) {
            throw new BusinessException(400, "TEAM_TOOL_PARAMETERS_INVALID");
        }
        var result = operations.preview(actor.id(), run.toolId(), parameters);
        runs.markPreview(actor, runId, digest(result.commands()));
        return ApiResponse.success(result);
    }

    @PostMapping("/api/team-agent-runs/{runId}/execute")
    public ApiResponse<?> execute(@AuthenticationPrincipal SessionUser actor, @PathVariable long runId) {
        var pending = runs.require(actor, runId);
        runtimes.requireOwned(pending.runtimeId(), actor.id());
        String commandDigest = null;
        if (!pending.readOnly()) {
            try {
                Map<String, String> parameters = mapper.readValue(pending.parametersJson(), new TypeReference<>() {});
                commandDigest = digest(operations.preview(actor.id(), pending.toolId(), parameters).commands());
            } catch (com.fasterxml.jackson.core.JsonProcessingException invalid) {
                throw new BusinessException(400, "TEAM_TOOL_PARAMETERS_INVALID");
            }
        }
        var run = runs.consumeGrant(actor, runId, commandDigest);
        try {
            Map<String, String> parameters;
            try { parameters = mapper.readValue(run.parametersJson(), new TypeReference<>() {}); }
            catch (com.fasterxml.jackson.core.JsonProcessingException invalid) {
                throw new BusinessException(400, "TEAM_TOOL_PARAMETERS_INVALID");
            }
            var result = operations.executeApprovedTeamRun(actor.id(), run.runtimeId(), run.toolId(), parameters,
                    "team-run-" + runId);
            runs.finish(actor, runId, result.status().equals("SUCCEEDED") ? "SUCCEEDED" : "FAILED");
            return ApiResponse.success(result);
        } catch (RuntimeException failure) {
            try { runs.finish(actor, runId, "FAILED"); } catch (RuntimeException ignored) { }
            throw failure;
        }
    }

    public record CreateInput(@NotNull Long versionId, @NotBlank String runtimeId, @NotBlank String toolId,
                              Map<String, String> parameters) {}

    private static String digest(java.util.List<String> commands) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(String.join("\n", commands).getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
}
