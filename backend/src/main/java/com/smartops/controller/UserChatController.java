package com.smartops.controller;

import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.security.SessionUser;
import com.smartops.service.ModelConnectionService;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/chat/connections")
public class UserChatController {
    private final ModelConnectionService models;
    public UserChatController(ModelConnectionService models) { this.models = models; }

    @PostMapping("/{id}/invoke")
    public ModelInvocationResponse invoke(@AuthenticationPrincipal SessionUser user, @PathVariable Long id,
            @Valid @RequestBody ModelInvocationRequest request) {
        return models.invoke(user.id(), id, request);
    }
}
