package com.smartops.entity;

import com.smartops.module.incident.IncidentRelationType;
import lombok.Data;

import java.time.LocalDateTime;

/** 事件关联：把告警、Agent Run、知识条目、执行证据挂到事件上。 */
@Data
public class IncidentRelation {

    private Long id;
    private Long incidentId;
    private IncidentRelationType relationType;
    private Long refId;
    private String refType;
    private LocalDateTime createdAt;
}
