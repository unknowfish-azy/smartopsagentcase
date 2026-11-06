package com.smartops.experiment;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.experiment.ExperimentService.DrillInput;
import com.smartops.experiment.ExperimentService.DrillView;
import com.smartops.experiment.ExperimentService.EvaluationInput;
import com.smartops.experiment.ExperimentService.EvaluationView;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;

/**
 * OPS-16：多集群/边缘/故障演练的评估与可退出验证接口。
 *
 * <p>不提供任何集群变更动作；引入与否由评估事实与演练证据决定，
 * {@code canAdopt} 只有在"有 VERIFIED 隔离演练 + 卸载已留证"时才为 true。</p>
 */
@RestController
@RequestMapping("/api/experiments")
public class ExperimentController {

    private final ExperimentService experiments;

    public ExperimentController(ExperimentService experiments) {
        this.experiments = experiments;
    }

    @GetMapping("/evaluations")
    public ApiResponse<List<EvaluationView>> evaluations(
            @CurrentUser Long userId) {
        return ApiResponse.success(experiments.listEvaluations(userId));
    }

    @PostMapping("/evaluations")
    public ApiResponse<EvaluationView> createEvaluation(
            @CurrentUser Long userId,
            @Valid @RequestBody EvaluationRequest request) {
        return ApiResponse.success(experiments.createEvaluation(userId, new EvaluationInput(
                request.component(), request.title(), request.necessity(), request.businessTrigger(),
                request.controlPlane(), request.permissions(), request.compatibility(),
                request.costNote(), request.uninstallSteps())));
    }

    @PostMapping("/evaluations/{evaluationId}/drills")
    public ApiResponse<DrillView> drill(
            @CurrentUser Long userId,
            @PathVariable long evaluationId,
            @Valid @RequestBody DrillRunRequest request) {
        return ApiResponse.success(experiments.recordDrill(userId, evaluationId, new DrillInput(
                request.mode(), request.scope(), request.startedAt(), request.finishedAt(),
                request.stopConditions(), request.stopTriggered(), request.stopEvidence(),
                request.recoveryEvidence(), request.backupDrillId())));
    }

    @PostMapping("/evaluations/{evaluationId}/exit")
    public ApiResponse<EvaluationView> exit(
            @CurrentUser Long userId,
            @PathVariable long evaluationId,
            @Valid @RequestBody ExitRequest request) {
        return ApiResponse.success(experiments.recordExit(userId, evaluationId, request.evidence()));
    }

    public record EvaluationRequest(@NotBlank String component, @NotBlank String title,
                                    @NotBlank String necessity, @NotBlank String businessTrigger,
                                    @NotBlank String controlPlane, @NotBlank String permissions,
                                    @NotBlank String compatibility, @NotBlank String costNote,
                                    @NotBlank String uninstallSteps) {}

    public record DrillRunRequest(String mode, String scope, Instant startedAt, Instant finishedAt,
                                  List<String> stopConditions, boolean stopTriggered, String stopEvidence,
                                  String recoveryEvidence, Long backupDrillId) {}

    public record ExitRequest(String evidence) {}
}
