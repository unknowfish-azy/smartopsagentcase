package com.smartops.dto;

import com.smartops.module.incident.IncidentRelationType;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/** 关联资源到事件的请求。 */
@Data
public class IncidentRelationRequest {

    @NotNull(message = "关联类型不能为空")
    private IncidentRelationType relationType;

    @NotNull(message = "关联目标 ID 不能为空")
    private Long refId;

    private String refType;
}
