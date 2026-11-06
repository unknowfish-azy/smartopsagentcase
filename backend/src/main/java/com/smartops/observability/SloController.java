package com.smartops.observability;

import com.smartops.common.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * OPS-10：SLI/SLO 与恢复判定只读接口。
 */
@RestController
@RequestMapping("/api/observability")
public class SloController {

    private final SloService sloService;

    public SloController(SloService sloService) {
        this.sloService = sloService;
    }

    @GetMapping("/slo")
    public ApiResponse<List<SloService.Evaluation>> slo(
            @RequestParam(defaultValue = "24") int windowHours) {
        return ApiResponse.success(sloService.evaluate(windowHours));
    }

    @GetMapping("/recovery/{contractRecordId}")
    public ApiResponse<SloService.RecoveryVerdict> recovery(
            @PathVariable long contractRecordId,
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId) {
        return ApiResponse.success(sloService.judgeRecovery(contractRecordId, userId));
    }
}
