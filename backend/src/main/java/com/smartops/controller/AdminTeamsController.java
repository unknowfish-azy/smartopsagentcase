package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import com.smartops.service.TeamWorkspaceService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin/teams")
public class AdminTeamsController {
    private final TeamWorkspaceService teams;
    public AdminTeamsController(TeamWorkspaceService teams) { this.teams = teams; }
    @GetMapping public ApiResponse<?> list(@AuthenticationPrincipal SessionUser actor, @RequestParam(required = false) String q, @RequestParam(required = false) String status, @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) { return ApiResponse.success(teams.adminList(actor, q, status, page, pageSize)); }
    @GetMapping("/{id}/members") public ApiResponse<?> members(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) { return ApiResponse.success(teams.adminMembers(actor, id)); }
    @PutMapping("/{id}/status") public ApiResponse<?> status(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @Valid @RequestBody StatusInput input) { teams.setStatus(actor, id, input.status()); return ApiResponse.success(); }
    public record StatusInput(@NotBlank String status) {}
}
