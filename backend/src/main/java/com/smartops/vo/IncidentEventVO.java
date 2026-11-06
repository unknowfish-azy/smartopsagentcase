package com.smartops.vo;

import com.smartops.module.incident.IncidentEventKind;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

/** 事件时间线视图对象。 */
@Data
@Builder
public class IncidentEventVO {

    private Long id;
    private Long incidentId;
    private LocalDateTime at;
    private Long actorId;
    private IncidentEventKind kind;
    private String detail;
}
