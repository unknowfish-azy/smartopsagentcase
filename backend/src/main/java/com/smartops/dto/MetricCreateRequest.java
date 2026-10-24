package com.smartops.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class MetricCreateRequest {

    @NotNull
    @Min(0)
    @Max(100)
    private Double cpuUsage;

    @NotNull
    @Min(0)
    @Max(100)
    private Double memoryUsage;

    @NotNull
    @Min(0)
    @Max(100)
    private Double diskUsage;

    private Double networkIn;

    private Double networkOut;

    private Double loadAverage;
}