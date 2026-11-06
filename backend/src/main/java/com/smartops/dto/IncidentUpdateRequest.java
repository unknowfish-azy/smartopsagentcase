package com.smartops.dto;

import com.smartops.module.incident.IncidentSeverity;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/** 更新事件基本信息请求。 */
@Data
public class IncidentUpdateRequest {

    @NotBlank(message = "事件标题不能为空")
    private String title;

    private String description;

    private IncidentSeverity severity;

    private IncidentSeverity priority;

    private String category;

    private String tags;

    private Long relatedAssetId;

    private String relatedAssetType;

    private String relatedService;

    private Integer slaTargetMinutes;
}
