package com.smartops.module.incident;

/** 事件来源。 */
public enum IncidentSource {
    /** 由告警自动生成。 */
    ALERT,
    /** 用户报障。 */
    USER_REPORT,
    /** Agent 诊断生成。 */
    AGENT_DIAGNOSIS,
    /** 人工创建。 */
    MANUAL
}
