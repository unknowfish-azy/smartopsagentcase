package com.smartops.module.incident;

/** 事件关联类型：把告警、Agent Run、知识条目、执行证据挂到事件上。 */
public enum IncidentRelationType {
    /** 关联 sentinel_alert。 */
    ALERT,
    /** 关联 operation_run_record / team_agent_run。 */
    AGENT_RUN,
    /** 关联 personal_knowledge_entry / knowledge_candidate。 */
    KNOWLEDGE,
    /** 关联 operation_run_evidence / 附件。 */
    EVIDENCE
}
