package com.smartops.dto.model;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;
import java.util.List;

@Data
public class GatewayChatRequest {
    @NotBlank private String model;
    @NotEmpty @Valid private List<Message> messages;
    private Double temperature = 0.2;
    private Boolean stream = false;
    @Data public static class Message { @NotBlank private String role; @NotBlank private String content; }
}
