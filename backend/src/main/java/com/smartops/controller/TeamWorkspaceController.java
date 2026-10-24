package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import com.smartops.service.TeamWorkspaceService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/teams")
public class TeamWorkspaceController {
    private final TeamWorkspaceService teams;
    private final com.smartops.service.TeamActivityService activity;
    private final com.smartops.service.TeamResourceGrantService grants;
    public TeamWorkspaceController(TeamWorkspaceService teams, com.smartops.service.TeamActivityService activity, com.smartops.service.TeamResourceGrantService grants) { this.teams = teams; this.activity = activity; this.grants = grants; }
    @GetMapping public ApiResponse<?> list(@AuthenticationPrincipal SessionUser actor, @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) { return ApiResponse.success(teams.list(actor, page, pageSize)); }
    @PostMapping public ApiResponse<?> create(@AuthenticationPrincipal SessionUser actor, @Valid @RequestBody TeamInput input) { return ApiResponse.success(teams.create(actor, input.name(), input.description())); }
    @GetMapping("/{id}") public ApiResponse<?> detail(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) { return ApiResponse.success(teams.detail(actor, id)); }
    @PutMapping("/{id}") public ApiResponse<?> update(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @Valid @RequestBody TeamInput input) { teams.update(actor, id, input.name(), input.description()); return ApiResponse.success(); }
    @GetMapping("/invitations") public ApiResponse<?> inbox(@AuthenticationPrincipal SessionUser actor, @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) { return ApiResponse.success(teams.inbox(actor, page, pageSize)); }
    @PostMapping("/{id}/invitations") public ApiResponse<?> invite(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @Valid @RequestBody InviteInput input) { teams.invite(actor, id, input.username(), input.role()); return ApiResponse.success(); }
    @PostMapping("/invitations/{invitationId}/respond") public ApiResponse<?> respond(@AuthenticationPrincipal SessionUser actor, @PathVariable long invitationId, @Valid @RequestBody Decision input) { teams.respond(actor, invitationId, input.accept()); return ApiResponse.success(); }
    @DeleteMapping("/{id}/invitations/{invitationId}") public ApiResponse<?> cancel(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @PathVariable long invitationId) { teams.cancelInvite(actor, id, invitationId); return ApiResponse.success(); }
    @PutMapping("/{id}/members/{userId}") public ApiResponse<?> role(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @PathVariable long userId, @Valid @RequestBody RoleInput input) { teams.changeMember(actor, id, userId, input.role()); return ApiResponse.success(); }
    @DeleteMapping("/{id}/members/{userId}") public ApiResponse<?> remove(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @PathVariable long userId) { teams.removeMember(actor, id, userId); return ApiResponse.success(); }
    @GetMapping("/{id}/activity") public ApiResponse<?> activity(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestParam(defaultValue = "50") int limit) { teams.detail(actor, id); return ApiResponse.success(activity.list(id, limit)); }
    @GetMapping("/{id}/resources/{resourceType}/{resourceId}") public ApiResponse<?> grants(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @PathVariable String resourceType, @PathVariable String resourceId) { return ApiResponse.success(grants.list(actor, id, resourceType, resourceId)); }
    @PostMapping("/{id}/resources/{resourceType}/{resourceId}/grants") public ApiResponse<?> grant(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @PathVariable String resourceType, @PathVariable String resourceId, @Valid @RequestBody GrantInput input) { grants.grant(actor, id, resourceType, resourceId, input.userId(), input.capability()); return ApiResponse.success(); }
    @DeleteMapping("/{id}/resources/{resourceType}/{resourceId}/grants/{userId}/{capability}") public ApiResponse<?> revoke(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @PathVariable String resourceType, @PathVariable String resourceId, @PathVariable long userId, @PathVariable String capability) { grants.revoke(actor, id, resourceType, resourceId, userId, capability); return ApiResponse.success(); }
    public record TeamInput(@NotBlank @Size(max = 80) String name, @Size(max = 500) String description) {}
    public record InviteInput(@NotBlank @Size(max = 64) String username, @NotBlank @Size(max = 16) String role) {}
    public record RoleInput(@NotBlank @Size(max = 16) String role) {}
    public record Decision(@NotNull Boolean accept) {}
    public record GrantInput(@NotNull Long userId, @NotBlank String capability) {}
}
