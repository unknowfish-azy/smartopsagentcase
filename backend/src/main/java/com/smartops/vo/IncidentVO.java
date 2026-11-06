package com.smartops.vo;

import com.smartops.module.incident.IncidentSeverity;
import com.smartops.module.incident.IncidentSource;
import com.smartops.module.incident.IncidentStatus;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

/** 事件 / 工单视图对象。 */
@Data
@Builder
public class IncidentVO {

    private Long id;
    private String title;
    private String description;
    private IncidentStatus status;
    private IncidentSeverity severity;
    private IncidentSeverity priority;
    private IncidentSource source;
    private String category;
    private String tags;
    private Long reporterId;
    private Long assigneeId;
    private Long relatedAssetId;
    private String relatedAssetType;
    private String relatedService;
    private Integer slaTargetMinutes;
    private LocalDateTime slaDeadline;
    private LocalDateTime acknowledgedAt;
    private LocalDateTime mitigatedAt;
    private LocalDateTime resolvedAt;
    private LocalDateTime closedAt;
    private String rootCause;
    private String resolution;
    private String postmortem;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
