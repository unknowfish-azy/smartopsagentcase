package com.smartops.vo;

import com.smartops.module.server.ServerStatus;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class ServerVO {

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