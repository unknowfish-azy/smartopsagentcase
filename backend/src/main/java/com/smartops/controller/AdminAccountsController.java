package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.AccountSessionRegistry;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.security.SessionRevocationService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.List;

@RestController
@RequestMapping("/api/admin")
public class AdminAccountsController {
    private final UserAccountService accounts;
    private final AccountSessionRegistry sessions;
    private final SecurityAuditService audit;
    private final SessionRevocationService revocations;

    public AdminAccountsController(UserAccountService accounts, AccountSessionRegistry sessions, SecurityAuditService audit, SessionRevocationService revocations) {
        this.accounts = accounts; this.sessions = sessions; this.audit = audit; this.revocations = revocations;
    }

    @GetMapping("/overview")
    public ApiResponse<Map<String, Long>> overview(@AuthenticationPrincipal SessionUser actor) {
        accounts.requirePlatformCapability(actor, "admin.users");
        return ApiResponse.success(accounts.overview());
    }

    @GetMapping("/registration")
    public ApiResponse<UserAccountService.RegistrationPolicy> registration(@AuthenticationPrincipal SessionUser actor) {
        accounts.requirePlatformCapability(actor, "admin.users");
        return ApiResponse.success(accounts.registrationPolicy());
    }

    @PutMapping("/registration")
    public ApiResponse<UserAccountService.RegistrationPolicy> registration(@AuthenticationPrincipal SessionUser actor, @Valid @RequestBody RegistrationSetting input) {
        return ApiResponse.success(accounts.setRegistration(input.enabled(), actor));
    }

    @GetMapping("/users")
    public ApiResponse<UserAccountService.AccountPage> users(@AuthenticationPrincipal SessionUser actor, @RequestParam(required = false) String q, @RequestParam(required = false) String role,
            @RequestParam(required = false) Boolean enabled, @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) {
        accounts.requirePlatformCapability(actor, "admin.users");
        return ApiResponse.success(accounts.list(q, role, enabled, page, pageSize));
    }

    @GetMapping("/users/{id}/context")
    public ApiResponse<?> context(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        return ApiResponse.success(accounts.accountContext(actor, id));
    }

    @GetMapping("/governance")
    public ApiResponse<?> governance(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(accounts.platformAdministrators(actor));
    }

    @PostMapping("/governance/{id}")
    public ApiResponse<?> appoint(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @RequestBody GovernanceInput input) {
        return ApiResponse.success(accounts.appointPlatformAdmin(actor, id, input.level(), input.capabilities()));
    }

    @DeleteMapping("/governance/{id}")
    public ApiResponse<?> revoke(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        return ApiResponse.success(accounts.revokePlatformAdmin(actor, id));
    }

    @PostMapping("/governance/transfer/{id}")
    public ApiResponse<?> transfer(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        accounts.transferPlatformRoot(actor, id);
        return ApiResponse.success();
    }

    @PostMapping("/users")
    public ApiResponse<UserAccountService.AccountView> create(@AuthenticationPrincipal SessionUser actor, @Valid @RequestBody CreateAccount input) {
        return ApiResponse.success(accounts.create(input.username(), input.password(), input.role(), input.deptId(), input.postId(), input.roleIds(), actor));
    }

    @PutMapping("/users/{id}")
    public ApiResponse<UserAccountService.AccountView> update(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @Valid @RequestBody UpdateAccount input) {
        return ApiResponse.success(accounts.update(id, input.role(), input.enabled(), input.deptId(), input.postId(), input.roleIds(), actor));
    }

    @PostMapping("/users/{id}/reset-password")
    public ApiResponse<Map<String, Boolean>> reset(@AuthenticationPrincipal SessionUser actor, @PathVariable long id, @Valid @RequestBody ResetPassword input) {
        accounts.resetPassword(id, input.password(), actor);
        return ApiResponse.success(Map.of("reauthenticate", true));
    }

    @GetMapping("/sessions")
    public ApiResponse<Map<String, Object>> sessions(@AuthenticationPrincipal SessionUser actor, HttpServletRequest request) {
        accounts.requirePlatformCapability(actor, "admin.users");
        return ApiResponse.success(Map.of("items", sessions.list(null, request.getSession(false))));
    }

    @DeleteMapping("/sessions/{id}")
    public ApiResponse<Void> revoke(@AuthenticationPrincipal SessionUser actor, @PathVariable String id) {
        revocations.revoke(actor, id, true);
        return ApiResponse.success();
    }

    @GetMapping("/audit")
    public ApiResponse<SecurityAuditService.AuditPage> audit(@AuthenticationPrincipal SessionUser actor, @RequestParam(required = false) String action, @RequestParam(required = false) String outcome,
            @RequestParam(required = false) String q, @RequestParam(required = false) String target, @RequestParam(required = false) String from,
            @RequestParam(required = false) String to, @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) {
        accounts.requirePlatformCapability(actor, "admin.audit");
        return ApiResponse.success(audit.list(action, outcome, q, target, from, to, page, pageSize));
    }

    @GetMapping("/audit/{id}")
    public ApiResponse<SecurityAuditService.AuditDetail> auditDetail(@AuthenticationPrincipal SessionUser actor, @PathVariable long id) {
        accounts.requirePlatformCapability(actor, "admin.audit");
        return ApiResponse.success(audit.detail(id));
    }

    @GetMapping("/governance/capabilities")
    public ApiResponse<?> capabilities(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(accounts.capabilityCatalog(actor));
    }

    public record CreateAccount(@NotBlank @Size(max = 64) String username, @NotBlank @Size(max = 128) String password, @NotBlank String role, Long deptId, Long postId, List<Long> roleIds) {}
    public record UpdateAccount(@NotBlank String role, @NotNull Boolean enabled, Long deptId, Long postId, List<Long> roleIds) {}
    public record ResetPassword(@NotBlank @Size(max = 128) String password) {}
    public record RegistrationSetting(@NotNull Boolean enabled) {}
    public record GovernanceInput(@NotBlank String level, List<String> capabilities) {}
}
