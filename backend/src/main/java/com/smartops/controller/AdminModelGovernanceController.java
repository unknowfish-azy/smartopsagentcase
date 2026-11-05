package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.service.ModelGovernanceService;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminModelGovernanceController {
    private final ModelGovernanceService governance;
    private final UserAccountService accounts;

    public AdminModelGovernanceController(ModelGovernanceService governance, UserAccountService accounts) {
        this.governance = governance;
        this.accounts = accounts;
    }

    /** 平台模型治理只读清单；与既有 admin 网关写入路径共用 admin.config 能力。 */
    @GetMapping("/api/admin/model-governance")
    public ApiResponse<?> snapshot(@AuthenticationPrincipal SessionUser actor) {
        accounts.requirePlatformCapability(actor, "admin.config");
        return ApiResponse.success(governance.snapshot());
    }
}
