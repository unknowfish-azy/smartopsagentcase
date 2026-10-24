package com.smartops.dto.operations;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class CreateOperationSessionRequest {
    @NotBlank private String name;
    @NotBlank private String protocol;
    @NotBlank private String host;
    @Min(1) @Max(65535) private Integer port = 22;
    @NotBlank private String username;
    private String password;
    private String identityPath;
    private Long groupId;
    private Long jumpSessionId;
    private String tagsJson;
    private String description;
    private String accent;
    private Boolean favorite;
}
