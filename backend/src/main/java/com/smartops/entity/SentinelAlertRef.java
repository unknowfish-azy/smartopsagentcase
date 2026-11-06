package com.smartops.entity;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 告警桥接视图：把 sentinel_alert 与其所属哨兵任务拼在一起，
 * 供事件中心"从告警创建事件"时读取，不修改任何既有告警逻辑。
 */
@Data
public class SentinelAlertRef {

    private Long id;
    private Long taskId;
    private String severity;
    private String status;
    private String title;
    private String metric;
    private String observedValue;
    private String thresholdValue;
    private LocalDateTime firedAt;
    private Long ticketId;
    private Long ownerId;
    private String taskName;
    private String runtimeId;
}
