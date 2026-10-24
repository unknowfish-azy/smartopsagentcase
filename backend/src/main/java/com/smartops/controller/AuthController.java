package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.admin.SysLoginLogService;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.security.AccountSessionRegistry;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionRevocationService;
import com.smartops.security.HumanVerificationService;
import com.smartops.security.AdminMfaService;
import com.smartops.security.MfaLoginService;
import com.smartops.exception.BusinessException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
public class AuthController {
    private final UserAccountService accounts;
    private final CsrfTokenRepository csrf;
    private final AccountSessionRegistry sessions;
    private final SecurityAuditService audit;
    private final SessionRevocationService revocations;
    private final HumanVerificationService humanVerification;
    private final AdminMfaService mfa;
    private final MfaLoginService mfaLogin;
    private final SysLoginLogService loginLog;

    public AuthController(UserAccountService accounts, CsrfTokenRepository csrf, AccountSessionRegistry sessions, SecurityAuditService audit, SessionRevocationService revocations, HumanVerificationService humanVerification, AdminMfaService mfa, MfaLoginService mfaLogin, SysLoginLogService loginLog) {
        this.accounts = accounts; this.csrf = csrf; this.sessions = sessions; this.audit = audit; this.revocations = revocations;
        this.humanVerification = humanVerification;
        this.mfa = mfa; this.mfaLogin = mfaLogin;
        this.loginLog = loginLog;
    }

    @GetMapping("/api/auth/human-verification")
    public ApiResponse<HumanVerificationService.Policy> humanVerification(@RequestParam String action, HttpServletRequest request, HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        return ApiResponse.success(humanVerification.policy(action, request));
    }

    /**
     * 本地图形点选校验：提交点击坐标换取一次性人机验证 token。
     * 成功/失败的审计事件沿用既有 HUMAN_VERIFY，与登录、注册处的记录方式保持一致。
     */
    @PostMapping("/api/auth/human-verification/verify")
    public ApiResponse<HumanVerificationService.Proof> verifyHumanVerification(@Valid @RequestBody HumanVerificationProofRequest input, HttpServletRequest request, HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        try {
            return ApiResponse.success(humanVerification.prove(input.action(), input.nonce(), clicks(input.clicks()), request));
        } catch (BusinessException rejected) {
            if (rejected.getCode() != 429) audit.record(null, "HUMAN_VERIFY", input.action(), rejected.getCode() == 503 ? "FAILURE" : "DENIED");
            throw rejected;
        }
    }

    private static List<int[]> clicks(List<HumanVerificationProofRequest.Click> clicks) {
        List<int[]> parsed = new java.util.ArrayList<>(clicks.size());
        for (HumanVerificationProofRequest.Click click : clicks) parsed.add(new int[] { click.x(), click.y() });
        return parsed;
    }

    @GetMapping("/api/auth/session")
    public ApiResponse<SessionResponse> session(Authentication authentication, CsrfToken token) {
        SessionUser user = authentication != null && authentication.getPrincipal() instanceof SessionUser identity ? identity : null;
        return ApiResponse.success(new SessionResponse(user, token.getToken()));
    }

    @PostMapping("/api/auth/login")
    public ApiResponse<?> login(@Valid @RequestBody LoginRequest input, HttpServletRequest request, HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        mfaLogin.clear(request.getSession(false));
        var permit = verifyHuman(humanVerification.loginAction(input.portal()), input.username(), input.humanToken(), request);
        SessionUser user;
        try { user = accounts.authenticate(input.username(), input.password(), request.getRemoteAddr(), input.portal()); }
        catch (BusinessException rejected) {
            if (rejected.getCode() == 401 || rejected.getCode() == 403) humanVerification.failedLogin(input.username(), request.getRemoteAddr());
            audit.failedLogin(input.username(), rejected.getCode() == 403 ? "DENIED" : "FAILURE");
            loginLog.recordFailure(input.username(), request.getRemoteAddr(), rejected.getMessage());
            throw rejected;
        } finally { permit.close(); }
        var mfaState = mfa.state(user.id());
        if ("admin".equals(user.role()) && mfaState.enabled()) {
            var session = request.getSession(true);
            SecurityContextHolder.clearContext();
            session.removeAttribute(HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
            sessions.forget(session);
            request.changeSessionId();
            return ApiResponse.success(mfaLogin.begin(user, mfaState.version(), session));
        }
        return establish(user, mfaState.version(), false, request, response);
    }

    @PostMapping("/api/auth/mfa/complete")
    public ApiResponse<SessionUser> completeMfa(@Valid @RequestBody MfaRequest input, HttpServletRequest request, HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        return mfaLogin.complete(request.getSession(false), input.challenge(), input.code(), request.getRemoteAddr(),
                verified -> establish(verified.user(), verified.version(), true, request, response));
    }

    @PostMapping("/api/auth/mfa/cancel")
    public ApiResponse<Void> cancelMfa(HttpServletRequest request) {
        mfaLogin.clear(request.getSession(false));
        return ApiResponse.success();
    }

    private ApiResponse<SessionUser> establish(SessionUser user, long version, boolean audited, HttpServletRequest request, HttpServletResponse response) {
        if (!audited) {
            if (!accounts.isCurrent(user) || mfa.state(user.id()).version() != version) throw new BusinessException(401, "账号安全状态已变更，请重新登录");
            audit.record(user, "LOGIN", user.id().toString(), "SUCCESS");
        }
        request.getSession(true);
        request.changeSessionId();
        request.getSession(false).setMaxInactiveInterval("admin".equals(user.portal()) ? 600 : 1800);
        request.getSession(false).setAttribute(AdminMfaService.SESSION_VERSION, version);
        String authority = user.mustChangePassword() ? "ROLE_PASSWORD_CHANGE" : "admin".equals(user.portal()) ? "ROLE_ADMIN" : "ROLE_OPERATOR";
        var authentication = UsernamePasswordAuthenticationToken.authenticated(user, null,
                List.of(new SimpleGrantedAuthority(authority)));
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
        new HttpSessionSecurityContextRepository().saveContext(context, request, response);
        csrf.saveToken(null, request, response);
        sessions.register(request.getSession(false), user);
        loginLog.recordSuccess(user.id(), user.username(), request.getRemoteAddr());
        return ApiResponse.success(user);
    }

    @GetMapping("/api/auth/registration")
    public ApiResponse<UserAccountService.RegistrationPolicy> registration() {
        return ApiResponse.success(accounts.registrationPolicy());
    }

    @PostMapping("/api/auth/register")
    public ApiResponse<UserAccountService.AccountView> register(@Valid @RequestBody RegistrationRequest input, HttpServletRequest request) {
        verifyHuman("register", input.username(), input.humanToken(), request);
        try {
            return ApiResponse.success(accounts.register(input.username(), input.password(), input.confirmPassword(), request.getRemoteAddr()));
        } catch (BusinessException rejected) {
            audit.record(null, "REGISTER", null, rejected.getCode() == 403 ? "DENIED" : "FAILURE");
            throw rejected;
        }
    }

    @PostMapping("/api/auth/password")
    public ApiResponse<Map<String, Boolean>> password(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody PasswordRequest input, HttpServletRequest request) {
        accounts.changePassword(user, input.currentPassword(), input.newPassword(), request.getRemoteAddr());
        return ApiResponse.success(Map.of("reauthenticate", true));
    }

    @GetMapping("/api/auth/profile")
    public ApiResponse<Map<String, String>> profile(@AuthenticationPrincipal SessionUser user) {
        return ApiResponse.success(accounts.profile(user));
    }

    @PutMapping("/api/auth/profile")
    public ApiResponse<Map<String, String>> updateProfile(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody ProfileRequest input) {
        return ApiResponse.success(accounts.updateProfile(user, input.realName(), input.phone(), input.email()));
    }

    @GetMapping("/api/auth/sessions")
    public ApiResponse<Map<String, Object>> sessions(@AuthenticationPrincipal SessionUser user, HttpServletRequest request) {
        return ApiResponse.success(Map.of("items", sessions.list(user.id(), request.getSession(false))));
    }

    @DeleteMapping("/api/auth/sessions/{id}")
    public ApiResponse<Void> revoke(@AuthenticationPrincipal SessionUser user, @PathVariable String id) {
        revocations.revoke(user, id, false);
        return ApiResponse.success();
    }

    public record SessionResponse(SessionUser user, String csrfToken) {}
    public record MfaRequest(@NotBlank @Size(max = 64) String challenge, @NotBlank @Size(max = 64) String code) {}
    private HumanVerificationService.Permit verifyHuman(String action, String username, String token, HttpServletRequest request) {
        try {
            return humanVerification.verify(action, username, token, request);
        } catch (BusinessException rejected) {
            if (rejected.getCode() != 429) audit.record(null, "HUMAN_VERIFY", action, rejected.getCode() == 503 ? "FAILURE" : "DENIED");
            throw rejected;
        }
    }

    public record LoginRequest(@NotBlank @Size(max = 64) String username, @NotBlank @Size(max = 128) String password, String portal, @Size(max = 2048) String humanToken) {}
    public record PasswordRequest(@NotBlank @Size(max = 128) String currentPassword, @NotBlank @Size(max = 128) String newPassword) {}
    public record ProfileRequest(@Size(max = 64) String realName, @Size(max = 32) String phone, @Size(max = 128) String email) {}
    public record RegistrationRequest(@NotBlank @Size(max = 64) String username, @NotBlank @Size(max = 128) String password, @NotBlank @Size(max = 128) String confirmPassword, @Size(max = 2048) String humanToken) {}

    /** 本地图形点选作答：action 与领取策略时一致，nonce 为会话挑战，clicks 为回报的点击坐标。 */
    public record HumanVerificationProofRequest(@NotBlank @Size(max = 32) String action, @NotBlank @Size(max = 64) String nonce,
            @NotEmpty @Size(max = 8) List<Click> clicks) {
        public record Click(@Min(0) @Max(300) int x, @Min(0) @Max(200) int y) {}
    }
}
