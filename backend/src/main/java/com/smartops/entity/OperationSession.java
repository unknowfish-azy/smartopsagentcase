package com.smartops.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class OperationSession {
    private Long id;
    private Long userId;
    private Long groupId;
    private String name;
    private String protocol;
    private String host;
    private Integer port;
    private String username;
    private Long credentialId;
    private String identityPath;
    private Long jumpSessionId;
    private String tagsJson;
    private String description;
    private String accent;
    private Boolean favorite;
    private String status;
    private LocalDateTime lastConnectedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
