package com.smartops.controller;

import com.smartops.dto.model.GatewayChatRequest;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.service.ModelGatewayService;
import jakarta.validation.Valid;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequiredArgsConstructor
public class ModelGatewayController {
    private final ModelGatewayService gateway;
    private final com.smartops.security.UserAccountService accounts;

    @PostMapping("/api/admin/model-gateway/keys")
    public ResponseEntity<ModelGatewayService.IssuedKey> issue(@AuthenticationPrincipal SessionUser user, @RequestBody Map<String, Object> body) {
        requireAdmin(user);
        Instant expires = body.get("expiresAt") == null ? null : Instant.parse(String.valueOf(body.get("expiresAt")));
        return ResponseEntity.ok(gateway.issueKey(user.id(), String.valueOf(body.getOrDefault("name", "gateway-key")), String.valueOf(body.getOrDefault("scope", "PERSONAL")), expires));
    }

    @PostMapping("/api/admin/model-gateway/keys/{id}/revoke")
    public ResponseEntity<Void> revoke(@AuthenticationPrincipal SessionUser user, @PathVariable Long id) { requireAdmin(user); gateway.revoke(user.id(), id); return ResponseEntity.noContent().build(); }

    @GetMapping("/api/model-gateway/keys")
    public List<Map<String, Object>> keys(@AuthenticationPrincipal SessionUser user) {
        requireUser(user);
        return gateway.keys(user.id());
    }

    @PostMapping("/api/model-gateway/keys")
    public ResponseEntity<ModelGatewayService.IssuedKey> issuePersonal(@AuthenticationPrincipal SessionUser user, @RequestBody Map<String, Object> body) {
        requireUser(user);
        Instant expires = body.get("expiresAt") == null ? null : Instant.parse(String.valueOf(body.get("expiresAt")));
        return ResponseEntity.ok(gateway.issueKey(user.id(), String.valueOf(body.getOrDefault("name", "gateway-key")), "PERSONAL", expires));
    }

    @PostMapping("/api/model-gateway/keys/{id}/revoke")
    public ResponseEntity<Void> revokePersonal(@AuthenticationPrincipal SessionUser user, @PathVariable Long id) {
        requireUser(user); gateway.revoke(user.id(), id); return ResponseEntity.noContent().build();
    }

    @PutMapping("/api/model-gateway/keys/{id}/quota")
    public ResponseEntity<Void> quota(@AuthenticationPrincipal SessionUser user, @PathVariable Long id, @RequestBody Map<String, Object> body) {
        requireUser(user);
        Long requests = body.get("requestLimit24h") == null ? null : Long.valueOf(String.valueOf(body.get("requestLimit24h")));
        Long tokens = body.get("tokenLimit24h") == null ? null : Long.valueOf(String.valueOf(body.get("tokenLimit24h")));
        gateway.setQuota(user.id(), id, requests, tokens);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/api/admin/model-gateway/groups")
    public ResponseEntity<Void> group(@AuthenticationPrincipal SessionUser user, @RequestBody Map<String, Object> body) {
        requireAdmin(user);
        gateway.configureGroup(user.id(), String.valueOf(body.get("slug")), String.valueOf(body.getOrDefault("name", body.get("slug"))), Long.valueOf(String.valueOf(body.get("connectionId"))));
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/model-gateway/groups")
    public List<Map<String, Object>> personalGroups(@AuthenticationPrincipal SessionUser user) {
        requireUser(user);
        return gateway.groups(user.id());
    }

    @PostMapping("/api/model-gateway/groups")
    public ResponseEntity<Void> personalGroup(@AuthenticationPrincipal SessionUser user, @RequestBody Map<String, Object> body) {
        requireUser(user);
        gateway.configurePersonalGroup(user.id(), String.valueOf(body.get("slug")), String.valueOf(body.getOrDefault("name", body.get("slug"))), Long.valueOf(String.valueOf(body.get("connectionId"))));
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/api/model-gateway/groups/{slug}")
    public ResponseEntity<Void> updatePersonalGroup(@AuthenticationPrincipal SessionUser user, @PathVariable String slug, @RequestBody Map<String, Object> body) {
        requireUser(user);
        gateway.renameGroup(user.id(), slug, String.valueOf(body.get("name")));
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/api/model-gateway/groups/{slug}")
    public ResponseEntity<Void> deletePersonalGroup(@AuthenticationPrincipal SessionUser user, @PathVariable String slug) {
        requireUser(user);
        gateway.deleteGroup(user.id(), slug);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/api/admin/model-gateway/groups/{slug}/routes")
    public ResponseEntity<Void> route(@AuthenticationPrincipal SessionUser user, @PathVariable String slug, @RequestBody Map<String, Object> body) {
        requireAdmin(user);
        gateway.addRoute(user.id(), slug, Long.valueOf(String.valueOf(body.get("connectionId"))), Integer.parseInt(String.valueOf(body.getOrDefault("priority", "100"))), Integer.parseInt(String.valueOf(body.getOrDefault("weight", "100"))));
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/api/model-gateway/groups/{slug}/routes")
    public ResponseEntity<Void> personalRoute(@AuthenticationPrincipal SessionUser user, @PathVariable String slug, @RequestBody Map<String, Object> body) {
        requireUser(user);
        gateway.addRoute(user.id(), slug, Long.valueOf(String.valueOf(body.get("connectionId"))), Integer.parseInt(String.valueOf(body.getOrDefault("priority", "100"))), Integer.parseInt(String.valueOf(body.getOrDefault("weight", "100"))));
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/api/model-gateway/groups/{slug}/routes/{id}")
    public ResponseEntity<Void> updatePersonalRoute(@AuthenticationPrincipal SessionUser user, @PathVariable String slug, @PathVariable Long id, @RequestBody Map<String, Object> body) {
        requireUser(user);
        gateway.updateRoute(user.id(), slug, id, Integer.parseInt(String.valueOf(body.getOrDefault("priority", "100"))), Integer.parseInt(String.valueOf(body.getOrDefault("weight", "100"))));
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/api/model-gateway/groups/{slug}/routes/{id}/status")
    public ResponseEntity<Void> updatePersonalRouteStatus(@AuthenticationPrincipal SessionUser user, @PathVariable String slug, @PathVariable Long id, @RequestBody Map<String, Object> body) {
        requireUser(user);
        gateway.setRouteEnabled(user.id(), slug, id, Boolean.parseBoolean(String.valueOf(body.getOrDefault("enabled", "false"))));
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/api/model-gateway/groups/{slug}/routes/{id}")
    public ResponseEntity<Void> deletePersonalRoute(@AuthenticationPrincipal SessionUser user, @PathVariable String slug, @PathVariable Long id) {
        requireUser(user);
        gateway.deleteRoute(user.id(), slug, id);
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/api/admin/model-gateway/routes/{id}/status")
    public ResponseEntity<Void> routeStatus(@AuthenticationPrincipal SessionUser user, @PathVariable Long id, @RequestBody Map<String, Object> body) {
        requireAdmin(user);
        gateway.setRouteEnabled(user.id(), id, Boolean.parseBoolean(String.valueOf(body.getOrDefault("enabled", "false"))));
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/api/admin/model-gateway/routes/{id}")
    public ResponseEntity<Void> deleteRoute(@AuthenticationPrincipal SessionUser user, @PathVariable Long id) {
        requireAdmin(user);
        gateway.deleteRoute(user.id(), id);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/model-gateway/groups/{slug}/routes")
    public List<Map<String, Object>> routes(@AuthenticationPrincipal SessionUser user, @PathVariable String slug) {
        requireUser(user);
        return gateway.routes(user.id(), slug);
    }

    @PutMapping("/api/model-gateway/groups/{slug}/quota")
    public ResponseEntity<Void> groupQuota(@AuthenticationPrincipal SessionUser user, @PathVariable String slug, @RequestBody Map<String, Object> body) {
        requireUser(user);
        Long requests = body.get("requestLimit24h") == null ? null : Long.valueOf(String.valueOf(body.get("requestLimit24h")));
        Long tokens = body.get("tokenLimit24h") == null ? null : Long.valueOf(String.valueOf(body.get("tokenLimit24h")));
        gateway.setGroupQuota(user.id(), slug, requests, tokens);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/model-gateway/analytics")
    public Map<String, Object> analytics(@AuthenticationPrincipal SessionUser user) {
        requireUser(user);
        return gateway.analytics(user.id());
    }

    @GetMapping("/v1/models")
    public Map<String, Object> models(@RequestHeader(value = "Authorization", required = false) String authorization) {
        return Map.of("object", "list", "data", gateway.models(gateway.authenticate(bearer(authorization))));
    }

    @PostMapping("/v1/chat/completions")
    public ResponseEntity<?> chat(@RequestHeader(value = "Authorization", required = false) String authorization, @Valid @RequestBody GatewayChatRequest request) {
        if (request.getTemperature() != null && (request.getTemperature() < 0 || request.getTemperature() > 2)) throw new BusinessException(400, "Invalid temperature");
        if (request.getMessages().size() > 50 || request.getMessages().stream().anyMatch(m -> !List.of("system", "user", "assistant").contains(m.getRole()) || m.getContent().length() > 12000)) throw new BusinessException(400, "Invalid messages");
        String system = request.getMessages().stream().filter(m -> "system".equals(m.getRole())).map(GatewayChatRequest.Message::getContent).findFirst().orElse(null);
        String prompt = request.getMessages().stream().filter(m -> !"system".equals(m.getRole())).map(m -> m.getRole() + ": " + m.getContent()).reduce((a, b) -> a + "\n" + b).orElse("");
        if (prompt.isBlank() || prompt.length() > 12000) throw new BusinessException(400, "Invalid prompt");
        ModelInvocationRequest internal = new ModelInvocationRequest(); internal.setPrompt(prompt); internal.setSystemPrompt(system); internal.setTemperature(request.getTemperature());
        var result = gateway.invoke(gateway.authenticate(bearer(authorization)), request.getModel(), internal);
        String content = result.getContent() == null ? "" : result.getContent();
        if (Boolean.TRUE.equals(request.getStream())) {
            String id = "chatcmpl-" + UUID.randomUUID();
            String chunk = "data: {\"id\":\"" + id + "\",\"object\":\"chat.completion.chunk\",\"created\":" + Instant.now().getEpochSecond() + ",\"model\":\"" + request.getModel() + "\",\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":" + jsonString(content) + "},\"finish_reason\":null}]}\n\ndata: {\"id\":\"" + id + "\",\"object\":\"chat.completion.chunk\",\"created\":" + Instant.now().getEpochSecond() + ",\"model\":\"" + request.getModel() + "\",\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n";
            return ResponseEntity.ok().header("Content-Type", "text/event-stream").body(chunk);
        }
        return ResponseEntity.ok(Map.of("id", "chatcmpl-" + UUID.randomUUID(), "object", "chat.completion", "created", Instant.now().getEpochSecond(), "model", request.getModel(), "choices", List.of(Map.of("index", 0, "message", Map.of("role", "assistant", "content", content), "finish_reason", "stop")), "usage", result.getUsage() == null ? Map.of() : result.getUsage()));
    }

    private String jsonString(String value) { return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\r", "\\r").replace("\n", "\\n") + "\""; }

    private String bearer(String value) { if (value == null || !value.startsWith("Bearer ")) throw new BusinessException(401, "Bearer key required"); return value.substring(7).trim(); }
    private void requireAdmin(SessionUser user) { if (user == null || !"admin".equals(user.role())) throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.FORBIDDEN, "Admin role required"); accounts.requirePlatformCapability(user, "admin.config"); }
    private void requireUser(SessionUser user) { if (user == null) throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.UNAUTHORIZED, "Login required"); }

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<Map<String, Object>> gatewayError(BusinessException ex) {
        int status = ex.getCode() >= 400 && ex.getCode() <= 599 ? ex.getCode() : 400;
        return ResponseEntity.status(status).body(Map.of("error", Map.of("message", ex.getMessage(), "type", status == 401 ? "authentication_error" : status == 403 ? "permission_error" : status >= 500 ? "server_error" : "invalid_request_error")));
    }

    @ExceptionHandler({MethodArgumentNotValidException.class, HttpMessageNotReadableException.class})
    public ResponseEntity<Map<String, Object>> invalidGatewayRequest(Exception ex) {
        return ResponseEntity.badRequest().body(Map.of("error", Map.of("message", "Invalid request body", "type", "invalid_request_error")));
    }
}
