package com.smartops.module.incident;

/**
 * 事件 / 工单状态机。
 *
 * <p>OPEN -> ACK -> MITIGATING -> RESOLVED -> CLOSED</p>
 * <ul>
 *   <li>OPEN       新建，未确认</li>
 *   <li>ACK        已确认（有人接单）</li>
 *   <li>MITIGATING 处置中</li>
 *   <li>RESOLVED   已解决，待关闭</li>
 *   <li>CLOSED     已关闭（关闭时必须填写根因与复盘）</li>
 * </ul>
 */
public enum IncidentStatus {

    OPEN,
    ACK,
    MITIGATING,
    RESOLVED,
    CLOSED;

    /** 是否允许从当前状态转移到目标状态。 */
    public boolean canTransitionTo(IncidentStatus target) {
        if (target == null) return false;
        return switch (this) {
            case OPEN -> target == ACK || target == CLOSED;   // 误报可直接关闭
            case ACK -> target == MITIGATING || target == RESOLVED || target == CLOSED;
            // 处置中必须先标记解决，避免跳过复盘直接关单
            case MITIGATING -> target == RESOLVED;
            case RESOLVED -> target == CLOSED || target == MITIGATING; // 未解决可退回处置
            case CLOSED -> target == OPEN; // 允许重开
        };
    }

    public boolean isTerminal() {
        return this == CLOSED;
    }
}
