package com.smartops.finops;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.finops.FinOpsService.BudgetStatusView;
import com.smartops.finops.FinOpsService.BudgetView;
import com.smartops.finops.FinOpsService.CostIngestView;
import com.smartops.finops.FinOpsService.CostInput;
import com.smartops.finops.FinOpsService.RecommendationsView;
import com.smartops.finops.FinOpsService.SummaryView;
import com.smartops.finops.FinOpsService.TrendPoint;
import com.smartops.finops.FinOpsService.UsageInput;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;

/**
 * OPS-14：FinOps 成本归集、容量建议与预算异常接口。
 */
@RestController
@RequestMapping("/api/finops")
public class FinOpsController {

    private final FinOpsService finops;

    public FinOpsController(FinOpsService finops) {
        this.finops = finops;
    }

    @PostMapping("/costs")
    public ApiResponse<CostIngestView> costs(
            @CurrentUser Long userId,
            @Valid @RequestBody CostBatchRequest request) {
        return ApiResponse.success(finops.ingestCosts(userId, request.batchId(),
                request.billingMonth(), request.records()));
    }

    @GetMapping("/summary")
    public ApiResponse<SummaryView> summary(
            @CurrentUser Long userId,
            @RequestParam String month) {
        return ApiResponse.success(finops.summary(userId, month));
    }

    @GetMapping("/trend")
    public ApiResponse<List<TrendPoint>> trend(
            @CurrentUser Long userId,
            @RequestParam(defaultValue = "6") int months) {
        return ApiResponse.success(finops.trend(userId, months));
    }

    @PostMapping("/usage")
    public ApiResponse<Integer> usage(
            @CurrentUser Long userId,
            @Valid @RequestBody UsageBatchRequest request) {
        return ApiResponse.success(finops.recordUsage(userId, request.samples()));
    }

    @GetMapping("/recommendations")
    public ApiResponse<RecommendationsView> recommendations(
            @CurrentUser Long userId,
            @RequestParam String month,
            @RequestParam Instant windowStart,
            @RequestParam Instant windowEnd) {
        return ApiResponse.success(finops.recommendations(userId, month, windowStart, windowEnd));
    }

    @PostMapping("/budgets")
    public ApiResponse<BudgetView> budget(
            @CurrentUser Long userId,
            @Valid @RequestBody BudgetRequest request) {
        return ApiResponse.success(finops.createBudget(userId, request.name(), request.billingMonth(),
                request.currency(), request.amountMinor(), request.allocationKey()));
    }

    @GetMapping("/budgets/status")
    public ApiResponse<BudgetStatusView> budgetStatus(
            @CurrentUser Long userId,
            @RequestParam String month) {
        return ApiResponse.success(finops.budgetStatus(userId, month));
    }

    public record CostBatchRequest(@NotBlank String batchId, @NotBlank String billingMonth,
                                   List<CostInput> records) {}

    public record UsageBatchRequest(List<UsageInput> samples) {}

    public record BudgetRequest(@NotBlank String name, @NotBlank String billingMonth,
                                @NotBlank String currency, long amountMinor, String allocationKey) {}
}
