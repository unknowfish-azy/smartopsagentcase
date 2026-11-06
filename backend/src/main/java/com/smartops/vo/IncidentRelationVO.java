package com.smartops.vo;

import com.smartops.module.incident.IncidentRelationType;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

/** 事件关联视图对象。 */
@Data
@Builder
public class IncidentRelationVO {

    private Long id;
    private Long incidentId;
    private IncidentRelationType relationType;
    private Long refId;
    private String refType;
    private LocalDateTime createdAt;
}
