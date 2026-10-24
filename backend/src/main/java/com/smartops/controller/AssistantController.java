package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.security.SessionUser;
import com.smartops.service.AssistantService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/assistant")
public class AssistantController {
    private final AssistantService assistant;

    public AssistantController(AssistantService assistant) { this.assistant = assistant; }

    @GetMapping("/options")
    public ApiResponse<AssistantService.Options> options(@AuthenticationPrincipal SessionUser user) {
        return ApiResponse.success(assistant.options(user));
    }

    @PutMapping("/preference")
    public ApiResponse<Map<String, String>> preference(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody Preference input) {
        return ApiResponse.success(assistant.savePreference(user, input.providerKey()));
    }

    @PostMapping("/chat")
    public ApiResponse<AssistantService.ChatReply> chat(@AuthenticationPrincipal SessionUser user, @Valid @RequestBody ChatInput input) {
        var history = input.history() == null ? List.<Map<String, String>>of() : input.history().stream().map(turn -> Map.of("role", turn.role(), "content", turn.content())).toList();
        return ApiResponse.success(assistant.chat(user, input.providerKey(), input.message().trim(), history));
    }

    public record Preference(@NotBlank @Size(max = 64) String providerKey) {}
    public record Turn(@NotBlank @Pattern(regexp = "user|assistant") String role, @NotBlank @Size(max = 4000) String content) {}
    public record ChatInput(@Size(max = 64) String providerKey, @NotBlank @Size(max = 2000) String message, @Size(max = 12) List<@jakarta.validation.constraints.NotNull @Valid Turn> history) {}
}
