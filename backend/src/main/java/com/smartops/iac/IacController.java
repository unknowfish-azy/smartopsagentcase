package com.smartops.iac;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.iac.IacService.ApplyView;
import com.smartops.iac.IacService.Check;
import com.smartops.iac.IacService.DriftView;
import com.smartops.iac.IacService.PlanRequest;
import com.smartops.iac.IacService.PlanView;
import com.smartops.iac.IacService.ReleaseView;
import com.smartops.iac.TerraformPlanAnalyzer.Analysis;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * OPS-12：IaC / GitOps 只读分析与受控变更接口。
 */
@RestController
@RequestMapping("/api/iac")
public class IacController {

    private final IacService iac;

    public IacController(IacService iac) {
        this.iac = iac;
    }

    /** 只分析不落库：用于提交前检查 plan 的销毁动作与脱敏摘要。 */
    @PostMapping("/plans/analyze")
    public ApiResponse<Analysis> analyze(@Valid @RequestBody AnalyzeRequest request) {
        return ApiResponse.success(iac.analyze(request.planJson()));
    }

    @PostMapping("/plans")
    public ApiResponse<PlanView> plan(
            @CurrentUser Long userId,
            @RequestBody PlanRequest request) {
        return ApiResponse.success(iac.plan(userId, request));
    }

    @GetMapping("/plans/{planId}")
    public ApiResponse<PlanView> plan(
            @CurrentUser Long userId,
            @PathVariable long planId) {
        return ApiResponse.success(iac.detail(userId, planId));
    }

    @PostMapping("/plans/{planId}/approve")
    public ApiResponse<PlanView> approve(
            @CurrentUser Long userId,
            @PathVariable long planId,
            @RequestBody(required = false) ApproveRequest request) {
        return ApiResponse.success(iac.approve(userId, planId, request != null && request.confirmDestroy()));
    }

    @PostMapping("/plans/{planId}/dispatch")
    public ApiResponse<ApplyView> dispatch(
            @CurrentUser Long userId,
            @PathVariable long planId,
            @Valid @RequestBody DispatchRequest request) {
        return ApiResponse.success(iac.dispatch(userId, planId, request.confirmationNonce()));
    }

    @PostMapping("/applies/{applyId}/complete")
    public ApiResponse<ApplyView> complete(
            @CurrentUser Long userId,
            @PathVariable long applyId,
            @Valid @RequestBody CompleteRequest request) {
        return ApiResponse.success(iac.completeApply(userId, applyId,
                request.runTraceId(), request.exitCode()));
    }

    @PostMapping("/applies/{applyId}/verify")
    public ApiResponse<ApplyView> verify(
            @CurrentUser Long userId,
            @PathVariable long applyId,
            @Valid @RequestBody VerifyRequest request) {
        return ApiResponse.success(iac.verify(userId, applyId, request.checks()));
    }

    @GetMapping("/releases")
    public ApiResponse<List<ReleaseView>> releases(
            @CurrentUser Long userId,
            @RequestParam String workspace) {
        return ApiResponse.success(iac.releases(userId, workspace));
    }

    @GetMapping("/drift")
    public ApiResponse<DriftView> drift(
            @CurrentUser Long userId,
            @RequestParam String workspace) {
        return ApiResponse.success(iac.drift(userId, workspace));
    }

    public record AnalyzeRequest(@NotBlank String planJson) {}

    public record ApproveRequest(boolean confirmDestroy) {}

    public record DispatchRequest(@NotBlank String confirmationNonce) {}

    public record CompleteRequest(@NotBlank String runTraceId, Integer exitCode) {}

    public record VerifyRequest(List<Check> checks) {}
}
