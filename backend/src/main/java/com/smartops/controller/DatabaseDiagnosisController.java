package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.diagnostics.database.DatabaseDiagnosisRequest;
import com.smartops.diagnostics.database.DatabaseDiagnosisService;
import com.smartops.diagnostics.database.DatabaseDiagnosisService.DatabaseDiagnosisResult;
import com.smartops.security.SessionUser;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 数据库真实诊断入口（OPS-07）。
 *
 * <p>只读：请求体只声明目标与凭据引用，不接收任意 SQL；实际语句由适配器固定给出。</p>
 */
@RestController
@RequestMapping("/api/operations")
public class DatabaseDiagnosisController {

    private final DatabaseDiagnosisService service;

    public DatabaseDiagnosisController(DatabaseDiagnosisService service) {
        this.service = service;
    }

    @PostMapping("/database/diagnose")
    public ApiResponse<DatabaseDiagnosisResult> diagnose(
            @CurrentUser Long userId,
            @Valid @RequestBody DatabaseDiagnosisRequest request) {
        SessionUser actor = new SessionUser(userId, "user-" + userId, "user");
        return ApiResponse.success(service.diagnose(actor, request));
    }
}
