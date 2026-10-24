package com.smartops.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class OperationCredential {
    private Long id;
    private Long userId;
    private String name;
    private String type;
    private String secretCiphertext;
    private String last4;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
