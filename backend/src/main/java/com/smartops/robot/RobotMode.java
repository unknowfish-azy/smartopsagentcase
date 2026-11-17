package com.smartops.robot;

import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

/**
 * 巡检机器人运行态与状态机转移表。
 *
 * <p>双态互斥：{@code AUTONOMOUS} 与 {@code HUMAN_CONTROL} 不能同时成立；
 * 任何状态都可进入 {@code E_STOP}，但只有人工复位能离开；
 * 非法转移一律 409（{@code ROBOT_INVALID_TRANSITION}），不做隐式纠正。</p>
 */
public enum RobotMode {
    /** 桥未连接或设备未上电。 */
    OFFLINE,
    /** 在线且空闲，可受理任务或遥控接管。 */
    IDLE,
    /** 自主态：模型大脑驱动。 */
    AUTONOMOUS,
    /** 人工态：遥控链路驱动。 */
    HUMAN_CONTROL,
    /** 急停：仅人工复位可离开。 */
    E_STOP,
    /** 故障：心跳丢失、低电、蓝牙错误等，需人工复位。 */
    FAULT;

    private static final Map<RobotMode, Set<RobotMode>> TRANSITIONS = Map.of(
            OFFLINE, EnumSet.of(IDLE),
            IDLE, EnumSet.of(AUTONOMOUS, HUMAN_CONTROL, E_STOP, FAULT, OFFLINE),
            AUTONOMOUS, EnumSet.of(IDLE, HUMAN_CONTROL, E_STOP, FAULT),
            HUMAN_CONTROL, EnumSet.of(IDLE, E_STOP, FAULT),
            E_STOP, EnumSet.of(IDLE, OFFLINE),
            FAULT, EnumSet.of(IDLE, OFFLINE)
    );

    /** 是否允许从当前态转移到目标态。 */
    public boolean canTransitTo(RobotMode target) {
        return target != null && TRANSITIONS.getOrDefault(this, Set.of()).contains(target);
    }

    /** 该状态下是否允许下发运动类命令（人工态仅 HUMAN_CONTROL，自主态由大脑驱动）。 */
    public boolean acceptsMotionCommand() {
        return this == HUMAN_CONTROL;
    }

    /** 该状态下是否允许受理自主巡检任务。 */
    public boolean acceptsTask() {
        return this == IDLE;
    }
}
