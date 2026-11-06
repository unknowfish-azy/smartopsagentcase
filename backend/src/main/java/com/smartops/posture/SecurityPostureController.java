package com.smartops.posture;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.posture.SecurityPostureService.FindingInput;
import com.smartops.posture.SecurityPostureService.FindingView;
import com.smartops.posture.SecurityPostureService.ReportInput;
import com.smartops.posture.SecurityPostureService.ReportView;
import com.smartops.posture.SecurityPostureService.SummaryView;
import com.smartops.posture.SecurityPostureService.VerifyView;
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

import java.time.Instant;
import java.util.List;

/**
 * OPS-15：第三方安全/配置报告接入、修复复测与例外接口。
 *
 * <p>主动扫描不在本接口范围内：它会消耗集群与镜像仓库资源，
 * 必须另立资源预算后再接入，不能借"报告导入"冒充"已扫描"。</p>
 */
@RestController
@RequestMapping("/api/security")
public class SecurityPostureController {

    private final SecurityPostureService posture;

    public SecurityPostureController(SecurityPostureService posture) {
        this.posture = posture;
    }

    @PostMapping("/reports")
    public ApiResponse<ReportView> reports(
            @CurrentUser Long userId,
            @Valid @RequestBody ReportRequest request) {
        return ApiResponse.success(posture.ingestReport(userId, new ReportInput(
                request.reportRef(), request.tool(), request.toolVersion(), request.scope(), request.target(),
                request.startedAt(), request.finishedAt(), request.sourceRef(), request.contentSha256(),
                request.findings())));
    }

    @PostMapping("/findings/{findingId}/verify-fix")
    public ApiResponse<VerifyView> verifyFix(
            @CurrentUser Long userId,
            @PathVariable long findingId,
            @Valid @RequestBody VerifyFixRequest request) {
        return ApiResponse.success(posture.verifyFix(userId, findingId, request.reportRef()));
    }

    @PostMapping("/findings/{findingId}/exception")
    public ApiResponse<FindingView> exception(
            @CurrentUser Long userId,
            @PathVariable long findingId,
            @Valid @RequestBody ExceptionRequest request) {
        return ApiResponse.success(posture.exception(userId, findingId, request.until(), request.reason()));
    }

    @GetMapping("/summary")
    public ApiResponse<SummaryView> summary(
            @CurrentUser Long userId,
            @RequestParam(required = false) String target) {
        return ApiResponse.success(posture.summary(userId, target));
    }

    public record ReportRequest(@NotBlank String reportRef, @NotBlank String tool, @NotBlank String toolVersion,
                                @NotBlank String scope, @NotBlank String target, Instant startedAt,
                                Instant finishedAt, String sourceRef, String contentSha256,
                                List<FindingInput> findings) {}

    public record VerifyFixRequest(@NotBlank String reportRef) {}

    public record ExceptionRequest(Instant until, String reason) {}
}
