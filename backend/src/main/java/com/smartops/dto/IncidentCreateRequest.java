package com.smartops.dto;

import com.smartops.module.incident.IncidentSeverity;
import com.smartops.module.incident.IncidentSource;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/** 创建事件 / 工单请求。 */
@Data
public class IncidentCreateRequest {

    @NotBlank(message = "事件标题不能为空")
    private String title;

    private String description;

    private IncidentSeverity severity = IncidentSeverity.P3;

    private IncidentSeverity priority = IncidentSeverity.P3;

    private IncidentSource source = IncidentSource.MANUAL;

    private String category;

    private String tags;

    private Long reporterId;

    private Long assigneeId;

    private Long relatedAssetId;

    private String relatedAssetType;

    private String relatedService;

    /** SLA 目标时长（分钟），为空则不设 SLA。 */
    private Integer slaTargetMinutes;
}
