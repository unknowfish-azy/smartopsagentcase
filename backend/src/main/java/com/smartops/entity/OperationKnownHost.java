package com.smartops.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class OperationKnownHost {
    private Long id;
    private Long sessionId;
    private String host;
    private Integer port;
    private String algorithm;
    private String fingerprint;
    private String publicKey;
    private LocalDateTime trustedAt;
}
