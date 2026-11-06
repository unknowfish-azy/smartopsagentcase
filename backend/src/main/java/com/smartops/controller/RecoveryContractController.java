package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.recovery.RecoveryContractService;
import com.smartops.security.SessionUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 恢复契约只读接口（浏览器侧）。
 *
 * <p>主体身份只取认证上下文 {@link SessionUser}，不接受 {@code X-User-Id} 之类自述头；
 * 越权查询按 404 返回，不区分"不存在"与"不属于你"。</p>
 */
@RestController
@RequestMapping("/api/recovery/contracts")
public class RecoveryContractController {

    private final RecoveryContractService service;

    public RecoveryContractController(RecoveryContractService service) {
        this.service = service;
    }

    @GetMapping
    public ApiResponse<Map<String, Object>> list(@AuthenticationPrincipal SessionUser user,
                                                 @RequestParam(required = false) Long runId,
                                                 @RequestParam(defaultValue = "1") int page,
                                                 @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.list(user.id(), runId, page, pageSize));
    }

    @GetMapping("/{id}")
    public ApiResponse<Map<String, Object>> detail(@AuthenticationPrincipal SessionUser user,
                                                   @PathVariable Long id) {
        return ApiResponse.success(service.detail(user.id(), id));
    }

    @GetMapping("/{id}/replay")
    public ApiResponse<Map<String, Object>> replay(@AuthenticationPrincipal SessionUser user,
                                                   @PathVariable Long id) {
        return ApiResponse.success(service.replay(user.id(), id));
    }
}
