"""简化版四足/人形/蜘蛛步态解算器（Python 版）。

用途：sim.py 模拟器输出 joints 字段，让前端验证「真机关节直驱」链路——
     模拟器不跑真机 SDK，只做简化步态动画，关节名与各形态 rig.json 一致。

四足 (DOG)：go2 官方 12 关节，home 站立 hip=0 / thigh=0.9 / calf=-1.8
人形 (ROBOT)：g1 官方 23 关节，home 站立 thigh=0 / calf=0.06 / elbow=1.4
蜘蛛 (SPIDER)：8 足 16 关节，home 站立 hip=0 / knee=-0.66（与 spider-bot.rig.json 同名）
"""

from __future__ import annotations

import math
import time


# ------------------------------------------------------------------
# 四足步态：周期正弦 + 120° 相位差（对侧腿同相，同侧前后腿 180° 反相）
# ------------------------------------------------------------------

_QUADRUPED_HOME = {
    'hip': 0.0,
    'thigh': 0.9,   # MJCF go2.xml keyframe
    'calf': -1.8,
}
# 行走时的角度增量幅值（弧度）
_QUADRUPED_AMP = {
    'hip': 0.08,
    'thigh': 0.55,
    'calf': 0.65,
}
# 四条腿的相位（rad）：FL=0, FR=π, RL=π, RR=0 → 对角步态
_QUADRUPED_PHASE = {
    'FL': 0.0,
    'FR': math.pi,
    'RL': math.pi,
    'RR': 0.0,
}


def quadruped_joints(linear_x: float, angular: float, t: float) -> dict[str, float]:
    """输出 go2 rig.json 关节名 → 弧度。

    Args:
        linear_x: 前进速度（-1..1）
        angular: 转向速度（-1..1）
        t: 时间（秒）
    """
    speed = max(abs(linear_x), abs(angular))
    # 周期：站立 0Hz → 行走 3.5Hz（宇树 Go2 trot gait）
    freq = 3.5 if speed > 0.01 else 0.0
    if freq == 0:
        phase = 0.0
    else:
        phase = 2 * math.pi * freq * t

    joints = {}
    for leg in ('FL', 'FR', 'RL', 'RR'):
        leg_phase = phase + _QUADRUPED_PHASE[leg]
        # 转向时腿要展开：内侧腿外展为负、外侧腿外展为正
        side_sign = 1 if leg.endswith('L') else -1
        # FL/RR 走直线时同相，转向时外展相反
        turn_bias = angular * 0.15 * side_sign * (1 if leg in ('FL', 'RR') else -1)
        hip_q = _QUADRUPED_HOME['hip'] + turn_bias + _QUADRUPED_AMP['hip'] * math.sin(leg_phase) * side_sign
        # thigh 和 calf 绕 +Y，前摆正（-增量）、屈膝正（+增量），这里简化为同向正弦
        thigh_q = _QUADRUPED_HOME['thigh'] - _QUADRUPED_AMP['thigh'] * math.sin(leg_phase) * (0.3 + 0.7 * speed)
        calf_q = _QUADRUPED_HOME['calf'] - _QUADRUPED_AMP['calf'] * abs(math.sin(leg_phase)) * (0.3 + 0.7 * speed)

        joints[f'{leg}_hip_joint'] = hip_q
        joints[f'{leg}_thigh_joint'] = thigh_q
        joints[f'{leg}_calf_joint'] = calf_q

    return joints


# ------------------------------------------------------------------
# 人形步态：双腿反相摆腿 + 双臂反向摆臂
# ------------------------------------------------------------------

_HUMANOID_HOME = {
    'hip_pitch': 0.0,
    'knee': 0.0,
    'ankle_pitch': 0.0,
    'shoulder_pitch': 0.0,
    'elbow': 1.4,   # 展示用自然下垂（官方零位 0 为 L 形前伸）
    'waist_yaw': 0.0,
}

_HUMANOID_AMP = {
    'hip_pitch': 0.5,
    'knee': 0.35,
    'ankle_pitch': 0.2,
    'shoulder_pitch': 0.35,
    'elbow': 0.15,
    'waist_yaw': 0.08,
}


def humanoid_joints(linear_x: float, angular: float, t: float) -> dict[str, float]:
    speed = max(abs(linear_x), abs(angular))
    freq = 2.0 if speed > 0.01 else 0.0
    phase = 2 * math.pi * freq * t if freq > 0 else 0.0

    joints = {}
    for side, prefix in (('L', 'left'), ('R', 'right')):
        leg_sign = 1 if side == 'L' else -1
        arm_sign = -leg_sign  # 双臂反向
        leg_phase = phase * leg_sign
        arm_phase = phase * arm_sign

        joints[f'{prefix}_hip_pitch_joint'] = (
            _HUMANOID_HOME['hip_pitch'] - _HUMANOID_AMP['hip_pitch'] * math.sin(leg_phase) * speed
        )
        # 膝只在摆腿向前半段弯曲
        knee_bend = max(0, math.sin(leg_phase)) if speed > 0.01 else 0
        joints[f'{prefix}_knee_joint'] = _HUMANOID_HOME['knee'] + _HUMANOID_AMP['knee'] * knee_bend * speed
        joints[f'{prefix}_ankle_pitch_joint'] = (
            _HUMANOID_HOME['ankle_pitch'] - _HUMANOID_AMP['ankle_pitch'] * math.sin(leg_phase * 0.5) * speed
        )
        joints[f'{prefix}_shoulder_pitch_joint'] = (
            _HUMANOID_HOME['shoulder_pitch'] - _HUMANOID_AMP['shoulder_pitch'] * math.sin(arm_phase) * speed
        )
        joints[f'{prefix}_elbow_joint'] = (
            _HUMANOID_HOME['elbow'] + _HUMANOID_AMP['elbow'] * abs(math.sin(arm_phase)) * speed
        )

    joints['waist_yaw_joint'] = _HUMANOID_HOME['waist_yaw'] + _HUMANOID_AMP['waist_yaw'] * math.sin(phase) * speed * 0.5
    return joints


# ------------------------------------------------------------------
# 蜘蛛步态：8 足交替四足（偶数腿 / 奇数腿反相），摆动相抬腿
# ------------------------------------------------------------------

_SPIDER_LEG_COUNT = 8
_SPIDER_HOME = {
    'hip': 0.0,
    'knee': -0.66,   # 与 frontend/public/models/robot/spider-bot.rig.json 的 home 一致
}
_SPIDER_AMP = {
    'hip': 0.28,
    'knee': 0.34,
}
_SPIDER_STRIDE_HZ = 1.3
_SPIDER_MAX_LINEAR = 0.5


def _spider_motion(linear_x: float, lateral_y: float, angular: float, t: float) -> tuple[float, float, float, int]:
    """归一化蜘蛛步态输入 → (振幅, 频率, 相位, 行进方向)。"""
    speed = max(abs(linear_x), abs(lateral_y), abs(angular))
    if speed <= 0.01:
        return 0.0, 0.0, 0.0, 1
    amp = min(1.0, speed / _SPIDER_MAX_LINEAR)
    forward = linear_x if abs(linear_x) > 1e-6 else lateral_y
    direction = -1 if forward < 0 else 1
    return amp, _SPIDER_STRIDE_HZ, 2 * math.pi * _SPIDER_STRIDE_HZ * t, direction


def spider_joints(linear_x: float, lateral_y: float, angular: float, t: float) -> dict[str, float]:
    """输出 spider-bot.rig.json 关节名 → 弧度（绝对角，含 home 站立姿态）。

    转向时按左右侧给 hip 一个小的外展偏置，与四足 turn_bias 口径保持一致的物理直觉。
    """
    amp, _, phase, direction = _spider_motion(linear_x, lateral_y, angular, t)
    joints = {}
    for i in range(_SPIDER_LEG_COUNT):
        leg_phase = phase + (0.0 if i % 2 == 0 else math.pi)
        # 腿上安装角 sin(a) >= 0 视为左侧（局部 +Z 为左），转向时外侧腿外展更大
        side_sign = 1 if math.sin(i / _SPIDER_LEG_COUNT * 2 * math.pi) >= 0 else -1
        turn_bias = angular * 0.12 * side_sign
        joints[f'Leg{i}_hip'] = (
            _SPIDER_HOME['hip'] + turn_bias + _SPIDER_AMP['hip'] * math.sin(leg_phase) * amp * direction
        )
        joints[f'Leg{i}_knee'] = (
            _SPIDER_HOME['knee'] + _SPIDER_AMP['knee'] * max(0.0, math.sin(leg_phase)) * amp
        )
    return joints


def spider_gait(linear_x: float, lateral_y: float, angular: float, t: float) -> dict:
    """蜘蛛形态专属遥测：步态相位、8 足触地状态、机身高度。"""
    amp, freq, phase, _ = _spider_motion(linear_x, lateral_y, angular, t)
    contacts = []
    for i in range(_SPIDER_LEG_COUNT):
        p = phase + (0.0 if i % 2 == 0 else math.pi)
        # 支撑相：sin <= 0（摆动相抬腿）；epsilon 吸收 sin(π)=1.22e-16 浮点正零
        contacts.append(math.sin(p) <= 1e-9)
    bob = 0.008 * abs(math.sin(phase)) * amp
    return {
        'legCount': _SPIDER_LEG_COUNT,
        'strideHz': round(freq, 2),
        'phase': round(phase % (2 * math.pi), 3),
        'footContacts': contacts,
        'bodyHeight': round(0.29 + bob, 3),
    }
