package com.smartops.controller;
import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import com.smartops.service.TeamNotificationService;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
@RestController
public class TeamNotificationController {
    private final TeamNotificationService notifications;
    public TeamNotificationController(TeamNotificationService notifications) { this.notifications = notifications; }
    @GetMapping("/api/team-notifications") public ApiResponse<?> list(@AuthenticationPrincipal SessionUser actor, @RequestParam(defaultValue = "false") boolean unreadOnly) { return ApiResponse.success(notifications.list(actor, unreadOnly)); }
    @PostMapping("/api/team-notifications/{id}/read") public ApiResponse<?> markRead(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) { notifications.markRead(actor, id); return ApiResponse.success(); }
}
