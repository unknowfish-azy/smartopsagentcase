package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import com.smartops.service.ChatAttachmentService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.nio.charset.StandardCharsets;
import java.util.List;

@RestController
@RequestMapping("/api/assistant/conversations")
public class ChatAttachmentController {
    private final ChatAttachmentService service;
    public ChatAttachmentController(ChatAttachmentService service) { this.service = service; }

    @ModelAttribute
    public void privateResponse(jakarta.servlet.http.HttpServletResponse response) { response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store"); }

    @GetMapping
    public ApiResponse<List<ChatAttachmentService.Conversation>> list(@AuthenticationPrincipal SessionUser user, @RequestParam(required = false) Long teamId) { return ApiResponse.success(service.list(user, teamId)); }
    @PostMapping
    public ApiResponse<ChatAttachmentService.Conversation> create(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody Create input) { return ApiResponse.success(service.create(user, input.id(), input.title(), input.teamId())); }
    @GetMapping("/{id}")
    public ApiResponse<ChatAttachmentService.Detail> detail(@AuthenticationPrincipal SessionUser user, @PathVariable String id) { return ApiResponse.success(service.detail(user, id)); }
    @PutMapping("/{id}")
    public ApiResponse<Void> rename(@AuthenticationPrincipal SessionUser user, @PathVariable String id, @Valid @RequestBody Rename input) { service.rename(user, id, input.title()); return ApiResponse.success(null); }
    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@AuthenticationPrincipal SessionUser user, @PathVariable String id) { service.delete(user, id); return ApiResponse.success(null); }
    @PostMapping(value = "/{id}/attachments", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<ChatAttachmentService.Attachment> upload(@AuthenticationPrincipal SessionUser user, @PathVariable String id, @RequestParam String requestId, @RequestPart MultipartFile file, @RequestParam(defaultValue = "FILE") String sourceType) { return ApiResponse.success(service.upload(user, id, requestId, file, sourceType)); }
    @GetMapping("/{id}/attachments/{attachmentId}/content")
    public ResponseEntity<byte[]> content(@AuthenticationPrincipal SessionUser user, @PathVariable String id, @PathVariable String attachmentId, @RequestParam(defaultValue = "false") boolean download) {
        var result = service.download(user, id, attachmentId);
        var disposition = download || !result.attachment().mediaType().startsWith("image/") ? ContentDisposition.attachment() : ContentDisposition.inline();
        return ResponseEntity.ok().header(HttpHeaders.CACHE_CONTROL, "no-store").header("X-Content-Type-Options", "nosniff")
                .header("Content-Security-Policy", "default-src 'none'; sandbox")
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.filename(result.attachment().name(), StandardCharsets.UTF_8).build().toString())
                .contentType(MediaType.parseMediaType(result.attachment().mediaType())).body(result.bytes());
    }
    @DeleteMapping("/{id}/attachments/{attachmentId}")
    public ApiResponse<Void> remove(@AuthenticationPrincipal SessionUser user, @PathVariable String id, @PathVariable String attachmentId) { service.removeStaged(user, id, attachmentId); return ApiResponse.success(null); }
    @PostMapping("/{id}/messages")
    public ApiResponse<ChatAttachmentService.Detail> append(@AuthenticationPrincipal SessionUser user, @PathVariable String id, @Valid @RequestBody Append input) { return ApiResponse.success(service.append(user, id, input.requestId(), input.text(), input.attachmentIds())); }

    public record Create(@NotBlank @Size(max = 36) String id, @NotBlank @Size(max = 80) String title, @Positive Long teamId) {}
    public record Rename(@NotBlank @Size(max = 80) String title) {}
    public record Append(@NotBlank @Size(max = 36) String requestId, @NotNull @Size(max = 2000) String text, @NotNull @Size(max = 5) List<@NotBlank @Size(max = 36) String> attachmentIds) {}
}
