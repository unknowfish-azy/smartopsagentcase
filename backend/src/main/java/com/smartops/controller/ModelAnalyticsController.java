package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.service.ModelAnalyticsService;
import com.smartops.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.math.BigDecimal;
import java.util.Map;

@RestController
@RequestMapping("/api/model-analytics")
@RequiredArgsConstructor
public class ModelAnalyticsController {
    private final ModelAnalyticsService service;
    @GetMapping
    public Map<String,Object> report(@CurrentUser Long userId,
            @RequestParam(required=false) String month, @RequestParam(required=false) Long connectionId) {
        return service.report(userId, parseMonth(month), connectionId);
    }
    public record BudgetRequest(String month, BigDecimal tokenLimit) {}
    @PutMapping("/budget")
    public Map<String,Object> budget(@CurrentUser Long userId, @RequestBody BudgetRequest request) {
        YearMonth month = parseMonth(request.month());
        Long limit = null;
        if (request.tokenLimit() != null) {
            try { limit = request.tokenLimit().longValueExact(); }
            catch (ArithmeticException ex) { throw new BusinessException("额度需为 0–1000000000000 的整数"); }
            if (limit < 0 || limit > 1_000_000_000_000L) throw new BusinessException("额度需为 0–1000000000000 的整数");
        }
        service.saveBudget(userId, month, limit);
        return service.report(userId, month, null);
    }
    private YearMonth parseMonth(String month) {
        if (month == null || month.isBlank()) return YearMonth.now(ZoneOffset.UTC);
        try {
            if (!month.matches("\\d{4}-\\d{2}")) throw new IllegalArgumentException();
            YearMonth value = YearMonth.parse(month);
            if (value.getYear() < 2000 || value.getYear() > 2100) throw new IllegalArgumentException();
            return value;
        } catch (Exception ex) { throw new BusinessException("月份格式应为 YYYY-MM，年份范围 2000–2100"); }
    }
}
