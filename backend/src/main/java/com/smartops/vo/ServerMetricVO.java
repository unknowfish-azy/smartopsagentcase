package com.smartops.vo;

import com.smartops.module.server.MetricStatus;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class ServerMetricVO {

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