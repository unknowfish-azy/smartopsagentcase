package com.smartops.entity;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 用户的大模型连接配置。
 */
@Data
public class ModelConnection {

    private Long id;

    private Long userId;

    private String name;

    private String provider;

    private String baseUrl;

    private String modelName;

    /**
     * 数据库存储的 AES-GCM 密文。
     *
     * 绝不能直接返回给前端。
     */
    private String apiKeyCiphertext;

    /**
     * API Key 最后四位。
     */
    private String apiKeyLast4;

    private Boolean enabled;

    private Integer timeoutSeconds;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}