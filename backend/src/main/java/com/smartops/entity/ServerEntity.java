package com.smartops.entity;

import com.smartops.module.server.ServerStatus;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ServerEntity {

    private Long id;

    private String name;

    private String host;

    private Integer port;

    private String os;

    private ServerStatus status;

    private String description;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}