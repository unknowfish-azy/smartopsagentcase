package com.smartops.controller;

import com.smartops.security.SessionUser;
import com.smartops.service.modelconfig.ModelConfigVersionService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 模型网关控制面接口：配置版本的创建、发布、回滚与查询。
 *
 * <p>这些接口不在对话请求链路上，只有人工或 CI 调用；发布后由
 * {@code ModelConfigRegistry} 热加载生效，不影响正在进行的对话。</p>
 */
@RestController
@RequiredArgsConstructor
public class ModelGatewayConfigController {

    private final ModelConfigVersionService versions;
    private final com.smartops.security.UserAccountService accounts;

    @GetMapping("/api/admin/model-gateway/config/versions")
    public List<Map<String, Object>> list(@AuthenticationPrincipal SessionUser user,
                                          @RequestParam(defaultValue = "50") int limit) {
        requireAdmin(user);
        return versions.list(limit);
    }

    @GetMapping("/api/admin/model-gateway/config/versions/{id}")
    public Map<String, Object> detail(@AuthenticationPrincipal SessionUser user, @PathVariable long id) {
        requireAdmin(user);
        return versions.get(id);
    }

    @PostMapping("/api/admin/model-gateway/config/versions")
    public ResponseEntity<Map<String, Object>> createDraft(@AuthenticationPrincipal SessionUser user,
                                                           @RequestBody(required = false) Map<String, Object> body) {
        requireAdmin(user);
        String summary = body == null ? null : text(body.get("summary"));
        return ResponseEntity.status(HttpStatus.CREATED).body(versions.createDraft(user.id(), summary));
    }

    @PostMapping("/api/admin/model-gateway/config/versions/{id}/activate")
    public Map<String, Object> activate(@AuthenticationPrincipal SessionUser user, @PathVariable long id,
                                        @RequestBody(required = false) Map<String, Object> body) {
        requireAdmin(user);
        return versions.activate(id, user.id(), percent(body == null ? null : body.get("percent")));
    }

    /** 提交审批，可同时申请灰度比例（1-100）。 */
    @PostMapping("/api/admin/model-gateway/config/versions/{id}/submit")
    public Map<String, Object> submit(@AuthenticationPrincipal SessionUser user, @PathVariable long id,
                                      @RequestBody(required = false) Map<String, Object> body) {
        requireAdmin(user);
        return versions.submit(id, user.id(), percent(body == null ? null : body.get("percent")));
    }

    @PostMapping("/api/admin/model-gateway/config/versions/{id}/approve")
    public Map<String, Object> approve(@AuthenticationPrincipal SessionUser user, @PathVariable long id,
                                       @RequestBody(required = false) Map<String, Object> body) {
        requireAdmin(user);
        return versions.approve(id, user.id(), body == null ? null : text(body.get("comment")));
    }

    @PostMapping("/api/admin/model-gateway/config/versions/{id}/reject")
    public Map<String, Object> reject(@AuthenticationPrincipal SessionUser user, @PathVariable long id,
                                      @RequestBody(required = false) Map<String, Object> body) {
        requireAdmin(user);
        return versions.reject(id, user.id(), body == null ? null : text(body.get("comment")));
    }

    /** 灰度健康对比：窗口内按配置版本聚合真实调用，给出转全量/回滚建议。 */
    @GetMapping("/api/admin/model-gateway/config/versions/{id}/compare")
    public Map<String, Object> compare(@AuthenticationPrincipal SessionUser user, @PathVariable long id,
                                       @RequestParam(defaultValue = "60") int minutes) {
        requireAdmin(user);
        return versions.compare(id, minutes);
    }

    /** 灰度转全量：把灰度中的版本提升到 100%，原全量版本退役。 */
    @PostMapping("/api/admin/model-gateway/config/versions/{id}/promote")
    public Map<String, Object> promote(@AuthenticationPrincipal SessionUser user, @PathVariable long id) {
        requireAdmin(user);
        return versions.promote(id, user.id());
    }

    @PostMapping("/api/admin/model-gateway/config/versions/{id}/rollback")
    public Map<String, Object> rollback(@AuthenticationPrincipal SessionUser user, @PathVariable long id,
                                        @RequestBody(required = false) Map<String, Object> body) {
        requireAdmin(user);
        return versions.rollback(id, user.id(), body == null ? null : text(body.get("reason")));
    }

    @DeleteMapping("/api/admin/model-gateway/config/versions/{id}")
    public ResponseEntity<Void> delete(@AuthenticationPrincipal SessionUser user, @PathVariable long id) {
        requireAdmin(user);
        versions.delete(id);
        return ResponseEntity.noContent().build();
    }

    /** 当前生效版本，普通用户可读，用于确认"我现在被哪份配置服务"。 */
    @GetMapping("/api/model-gateway/config")
    public Map<String, Object> current(@AuthenticationPrincipal SessionUser user) {
        if (user == null) {
            throw new org.springframework.web.server.ResponseStatusException(
                    org.springframework.http.HttpStatus.UNAUTHORIZED, "Login required");
        }
        return versions.currentEffective();
    }

    private void requireAdmin(SessionUser user) {
        if (user == null || !"admin".equals(user.role())) {
            throw new org.springframework.web.server.ResponseStatusException(
                    org.springframework.http.HttpStatus.FORBIDDEN, "Admin role required");
        }
        accounts.requirePlatformCapability(user, "admin.config");
    }

    private String text(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    /** 灰度比例：缺省视为全量 100，非数字交由服务层拒绝。 */
    private int percent(Object value) {
        if (value == null || String.valueOf(value).isBlank()) {
            return 100;
        }
        try {
            return Integer.parseInt(String.valueOf(value).trim());
        } catch (NumberFormatException ex) {
            throw new com.smartops.exception.BusinessException(400, "灰度比例必须是 1-100 的整数");
        }
    }
}
