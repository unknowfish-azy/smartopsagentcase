package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import com.smartops.service.TeamAgentService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/teams/{teamId}/agents")
public class TeamAgentController {
    private final TeamAgentService agents;

    public TeamAgentController(TeamAgentService agents) {
        this.agents = agents;
    }

    @GetMapping
    public ApiResponse<?> list(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId) {
        return ApiResponse.success(agents.list(actor, teamId));
    }

    @GetMapping("/catalog")
    public ApiResponse<?> catalog(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId) {
        return ApiResponse.success(agents.catalog(actor, teamId));
    }

    @PostMapping
    public ApiResponse<?> create(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId,
                                 @Valid @RequestBody CreateInput input) {
        return ApiResponse.success(agents.create(actor, teamId, input.name(), input.description()));
    }

    @GetMapping("/{agentId}")
    public ApiResponse<?> detail(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId,
                                 @PathVariable long agentId) {
        return ApiResponse.success(agents.detail(actor, teamId, agentId));
    }

    @GetMapping("/{agentId}/tools")
    public ApiResponse<?> tools(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId,
                                @PathVariable long agentId) {
        return ApiResponse.success(agents.availableTools(actor, teamId, agentId));
    }

    @PutMapping("/{agentId}/draft")
    public ApiResponse<?> saveDraft(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId,
                                    @PathVariable long agentId, @Valid @RequestBody DraftInput input) {
        agents.saveDraft(actor, teamId, agentId, input.prompt(), input.toolsJson(), input.expectedRevision());
        return ApiResponse.success();
    }

    @PostMapping("/{agentId}/publish")
    public ApiResponse<?> publish(@AuthenticationPrincipal SessionUser actor, @PathVariable long teamId,
                                  @PathVariable long agentId) {
        return ApiResponse.success(agents.publish(actor, teamId, agentId));
    }

    public record CreateInput(@NotBlank @Size(max = 120) String name, @Size(max = 500) String description) {}

    /**
     * 保存草稿。
     *
     * <p>{@code expectedRevision} 为可选乐观锁：传了就校验，没传就不校验（兼容旧前端）。
     * 不匹配时返回 409，避免后保存的人静默覆盖前一个人的修改。</p>
     */
    public record DraftInput(@NotBlank @Size(max = 20000) String prompt, @NotBlank String toolsJson,
                             Integer expectedRevision) {}
}
