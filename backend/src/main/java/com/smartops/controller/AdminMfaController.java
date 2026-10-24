package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
public class AdminMfaController {
    private final AdminMfaService mfa;
    private final SecurityNoticeService notices;
    public AdminMfaController(AdminMfaService mfa, SecurityNoticeService notices) {
        this.mfa = mfa; this.notices = notices;
    }

    @GetMapping("/api/admin/mfa")
    public ApiResponse<AdminMfaService.Status> status(@AuthenticationPrincipal SessionUser user, HttpServletResponse response) {
        noStore(response);
        return ApiResponse.success(mfa.status(user));
    }

    @PostMapping("/api/admin/mfa/setup")
    public ApiResponse<AdminMfaService.Enrollment> setup(@AuthenticationPrincipal SessionUser user, HttpServletRequest request, HttpServletResponse response) {
        noStore(response);
        return ApiResponse.success(mfa.setup(user, request.getSession(false)));
    }

    @PostMapping("/api/admin/mfa/enable")
    public ApiResponse<AdminMfaService.Mutation> enable(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody EnableRequest input, HttpServletRequest request, HttpServletResponse response) {
        noStore(response);
        var result = change(request, () -> mfa.enable(user, request.getSession(false), input.challenge(), input.code(), request.getRemoteAddr()));
        return ApiResponse.success(result);
    }

    @PostMapping("/api/admin/mfa/recovery")
    public ApiResponse<AdminMfaService.Mutation> recovery(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody CodeRequest input, HttpServletRequest request, HttpServletResponse response) {
        noStore(response);
        var result = change(request, () -> mfa.change(user, request.getSession(false), input.code(), request.getRemoteAddr(), false));
        return ApiResponse.success(result);
    }

    @PostMapping("/api/admin/mfa/disable")
    public ApiResponse<AdminMfaService.Mutation> disable(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody CodeRequest input, HttpServletRequest request, HttpServletResponse response) {
        noStore(response);
        var result = change(request, () -> mfa.change(user, request.getSession(false), input.code(), request.getRemoteAddr(), true));
        return ApiResponse.success(result);
    }

    @GetMapping("/api/admin/mfa/notices")
    public ApiResponse<List<SecurityNoticeService.Notice>> notices(@AuthenticationPrincipal SessionUser user, HttpServletResponse response) {
        noStore(response);
        return ApiResponse.success(notices.list(user));
    }

    @PostMapping("/api/auth/mfa/notices/{id}/read")
    public ApiResponse<Void> read(@AuthenticationPrincipal SessionUser user, @PathVariable long id) {
        notices.read(user, id);
        return ApiResponse.success();
    }

    private AdminMfaService.Mutation change(HttpServletRequest request, java.util.function.Supplier<AdminMfaService.Mutation> operation) {
        var current = request.getSession(false);
        synchronized (current) {
            var result = operation.get();
            try { if (request.getSession(false) == current) request.changeSessionId(); }
            catch (IllegalStateException expired) { }
            return result;
        }
    }
    private void noStore(HttpServletResponse response) { response.setHeader("Cache-Control", "no-store"); }
    public record CodeRequest(@NotBlank @Size(max = 64) String code) {}
    public record EnableRequest(@NotBlank @Size(max = 64) String challenge, @NotBlank @Size(max = 64) String code) {}
}
