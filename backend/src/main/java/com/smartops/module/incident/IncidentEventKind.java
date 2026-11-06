package com.smartops.module.incident;

/** 事件时间线条目类型。 */
public enum IncidentEventKind {
    /** 状态流转，detail 为 "OLD_STATUS -> NEW_STATUS"。 */
    STATUS_CHANGE,
    /** 评论，detail 为评论内容。 */
    COMMENT,
    /** 指派 / 转派，detail 为新负责人。 */
    ASSIGN,
    /** SLA 超时提醒。 */
    SLA_BREACH,
    /** 系统自动记录（如从告警创建）。 */
    SYSTEM,
    /** 关联资源变更。 */
    RELATION
}
