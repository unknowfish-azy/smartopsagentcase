package com.smartops.cloud;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 云账号只读接入与轻量 CMDB 的 HTTP 入口（OPS-02、OPS-03）。
 *
 * 所有接口都要求已登录；团队账号的成员/权限判定在 CloudAssetService 内完成，
 * 不依赖前端隐藏入口。
 */
@RestController
@RequestMapping("/api/cloud")
public class CloudAssetController {

    private final CloudAssetService service;

    public CloudAssetController(CloudAssetService service) {
        this.service = service;
    }

    @PostMapping("/accounts")
    public ApiResponse<CloudAssetService.AccountView> createAccount(
            @AuthenticationPrincipal SessionUser actor,
            @Valid @RequestBody CloudAssetService.CreateAccountRequest request) {
        return ApiResponse.success(service.createAccount(actor, request));
    }

    @GetMapping("/accounts")
    public ApiResponse<List<CloudAssetService.AccountView>> accounts(@AuthenticationPrincipal SessionUser actor) {
        return ApiResponse.success(service.accounts(actor));
    }

    @PostMapping("/accounts/{id}/sync")
    public ApiResponse<CloudAssetService.SyncResult> sync(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable long id) {
        return ApiResponse.success(service.sync(actor, id));
    }

    @GetMapping("/accounts/{id}/sync-runs")
    public ApiResponse<List<CloudAssetService.SyncRunResult>> syncRuns(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable long id,
            @RequestParam(defaultValue = "20") int limit) {
        return ApiResponse.success(service.syncRuns(actor, id, limit));
    }

    @GetMapping("/resources")
    public ApiResponse<CloudAssetService.ResourcePage> resources(
            @AuthenticationPrincipal SessionUser actor,
            @RequestParam(required = false) String business,
            @RequestParam(required = false) String environment,
            @RequestParam(name = "type", required = false) String resourceType,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.success(service.resources(actor, business, environment, resourceType, status, keyword, page, size));
    }

    @GetMapping("/resources/{uid}")
    public ApiResponse<CloudAssetService.ResourceView> resource(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable String uid) {
        return ApiResponse.success(service.resource(actor, uid));
    }

    @PostMapping("/resources/{uid}/status")
    public ApiResponse<CloudAssetService.ResourceView> markStatus(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable String uid,
            @Valid @RequestBody CloudAssetService.StatusRequest request) {
        return ApiResponse.success(service.markStatus(actor, uid, request));
    }

    @GetMapping("/business/{business}/impact")
    public ApiResponse<CloudAssetService.ImpactView> impact(
            @AuthenticationPrincipal SessionUser actor,
            @PathVariable String business,
            @RequestParam(required = false) String environment) {
        return ApiResponse.success(service.businessImpact(actor, business, environment));
    }

    @PostMapping("/relations")
    public ApiResponse<CloudAssetService.RelationView> declareRelation(
            @AuthenticationPrincipal SessionUser actor,
            @Valid @RequestBody CloudAssetService.DeclareRelationRequest request) {
        return ApiResponse.success(service.declareRelation(actor, request));
    }
}
