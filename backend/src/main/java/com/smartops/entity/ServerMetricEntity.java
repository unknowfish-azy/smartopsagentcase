package com.smartops.entity;

import com.smartops.module.server.MetricStatus;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ServerMetricEntity {

    private Long id;

    private Long serverId;

    private Double cpuUsage;

    private Double memoryUsage;

    private Double diskUsage;

    private Double networkIn;

    private Double networkOut;

    private Double loadAverage;

    private MetricStatus status;

    private LocalDateTime collectedAt;
}