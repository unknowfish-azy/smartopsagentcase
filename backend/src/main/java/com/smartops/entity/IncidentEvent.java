package com.smartops.entity;

import com.smartops.module.incident.IncidentEventKind;
import lombok.Data;

import java.time.LocalDateTime;

/** 事件时间线条目（状态流转、评论、系统记录）。不可修改。 */
@Data
public class IncidentEvent {

    private Long id;
    private Long incidentId;
    private LocalDateTime at;
    private Long actorId;
    private IncidentEventKind kind;
    private String detail;
}
