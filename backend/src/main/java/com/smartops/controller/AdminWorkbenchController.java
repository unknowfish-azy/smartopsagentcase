package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import com.smartops.service.AdminWorkbenchService;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminWorkbenchController {
    private final AdminWorkbenchService workbench;

    public AdminWorkbenchController(AdminWorkbenchService workbench) {
        this.workbench = workbench;
    }

    /** 管理总览待办：逐项按调用者能力与团队批准资格过滤，不返回无权限的统计。 */
    @GetMapping("/api/admin/workbench")
    public ApiResponse<?> workbench(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(workbench.workbench(actor));
    }
}
