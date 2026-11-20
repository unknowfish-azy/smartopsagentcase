"""宇树 unitree_legged_sdk 旧协议（UDP 端口 8000）LowState 解码。

契约：来自 unitree_legged_sdk/go1/include/unitree_legged_sdk/comm.h，
#pragma pack(1) 紧凑排列，C 端小端。
- LowState 原始长度 949 字节，UDP 实际 payload 可能更小（CRC 裁剪），按实际 struct 偏移读取。
- 本模块只负责把字节块 → {关节角: 弧度} 的纯函数映射，不做网络/订阅/错误重试。
- 电机索引：Go2 12 个电机（FL/FR/RL/RR × hip/thigh/calf），索引顺序按官方 go1_const.h。
  G1 人形仅支持 unitree_sdk2 (DDS) 协议，不走此适配层。
"""

from __future__ import annotations

import struct

# ------------------------------------------------------------------
# 结构格式（按 comm.h packed(1)）
# ------------------------------------------------------------------

# MotorState: uint8 mode + 7 float(q,dq,ddq,tauEst,q_raw,dq_raw,ddq_raw) + int8 temp + uint32 reserve[2]
_MOTOR_STATE_FMT = struct.Struct('<B7fB2I')
_MOTOR_STATE_SIZE = _MOTOR_STATE_FMT.size  # 38

# IMU: float[4] quat(w,x,y,z) + float[3] gyro + float[3] acc + float[3] rpy + int8 temp
_IMU_FMT = struct.Struct('<4f3f3f3fb')
_IMU_SIZE = _IMU_FMT.size  # 53

# LowState 各字段起始偏移
_LS_OFFSETS = {
    'head': 0,             # uint8[2] = 2
    'levelFlag': 2,        # uint8   = 1
    'frameReserve': 3,     # uint8   = 1
    'SN': 4,               # uint32[2] = 8
    'version': 12,         # uint32[2] = 8
    'bandWidth': 20,       # uint16   = 2
    'imu': 22,             # IMU      = 53 → 结束 75
    'motorState': 75,      # MotorState[20] = 20*38 = 760 → 结束 835
    'bms': 835,            # BmsState
    'footForce': 909,      # int16[4]
    'tick': 925,           # uint32
    'wirelessRemote': 929, # uint8[40]
    'crc': 973,            # uint32
}

_GO2_LEG_MOTORS = (
    ('FL', 'hip'), ('FL', 'thigh'), ('FL', 'calf'),
    ('FR', 'hip'), ('FR', 'thigh'), ('FR', 'calf'),
    ('RL', 'hip'), ('RL', 'thigh'), ('RL', 'calf'),
    ('RR', 'hip'), ('RR', 'thigh'), ('RR', 'calf'),
)


def _unpack(buf: bytes, offset: int, fmt: struct.Struct | str):
    if isinstance(fmt, str):
        fmt = struct.Struct(fmt)
    end = offset + fmt.size
    if len(buf) < end:
        return None
    return fmt.unpack_from(buf, offset)


def decode_low_state(buf: bytes) -> dict:
    """UDP LowState → 结构化 dict。字段全部以 dict 形式返回，缺失则为 None。"""
    if len(buf) < 75:  # 至少要有 IMU 区
        return {'ok': False, 'error': f'包长 {len(buf)} < 75 字节，不是合法 LowState'}

    result = {'ok': True}

    imu = _unpack(buf, _LS_OFFSETS['imu'], _IMU_FMT)
    if imu:
        result['imu'] = {
            'quat': list(imu[0:4]),       # [w,x,y,z]
            'gyro': list(imu[4:7]),       # [wx,wy,wz]
            'acc': list(imu[7:10]),       # [ax,ay,az]
            'rpy': list(imu[10:13]),      # [roll,pitch,yaw]
            'temp': imu[13],
        }

    if len(buf) >= _LS_OFFSETS['motorState'] + 20 * _MOTOR_STATE_SIZE:
        motors = []
        for i in range(20):
            ms = _unpack(buf, _LS_OFFSETS['motorState'] + i * _MOTOR_STATE_SIZE, _MOTOR_STATE_FMT)
            if ms is None:
                break
            motors.append({
                'mode': ms[0],
                'q': ms[1], 'dq': ms[2], 'ddq': ms[3],
                'tauEst': ms[4], 'temp': ms[9],
            })
        result['motorState'] = motors
    else:
        result['motorState'] = None

    tick = _unpack(buf, _LS_OFFSETS['tick'], '<I')
    if tick:
        result['tick'] = tick[0]

    return result


def go2_joint_dict(low_state: dict) -> dict[str, float] | None:
    """LowState → go2.rig.json 关节名 → 弧度的字典，或 None（包不完整）。"""
    motors = low_state.get('motorState')
    if not motors or len(motors) < 12:
        return None
    joints = {}
    for idx, (leg, part) in enumerate(_GO2_LEG_MOTORS):
        m = motors[idx]
        if m is None:
            return None
        joints[f'{leg}_{part}_joint'] = float(m['q'])
    return joints
