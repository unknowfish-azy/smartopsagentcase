"""自定义/人形机器人协议（占位，待真机抓包确认）。

对应 RobotRegistryService FORM_FACTORS 中的 "ROBOT" 类型，
通用形态（如人形双臂、带操作末端等）。
需要拿到真机的
- 服务 UUID 与 写/通知 特征值 UUID
- 指令字节格式（一般走厂商 SDK 的高层动作接口）
- 遥测帧格式（关节角/末端位姿/IMU）
确认后替换下方常量并实现 encode/decode；当前一切调用如实报错，不编造字节。
"""

from __future__ import annotations

from .base import BridgeProtocolError, ProtocolAdapter


class GenericBleRobotV1Adapter(ProtocolAdapter):
    PROTOCOL_ID = "generic-ble-robot-v1"

    SERVICE_UUID = ""       # TODO(真机抓包)
    WRITE_CHAR_UUID = ""    # TODO(真机抓包)
    NOTIFY_CHAR_UUID = ""   # TODO(真机抓包)

    def encode_command(self, command: dict) -> bytes:
        raise BridgeProtocolError("generic-ble-robot-v1 协议待真机 SDK 确认，拒绝编码未知字节")

    def decode_notification(self, data: bytes) -> dict | None:
        raise BridgeProtocolError("generic-ble-robot-v1 协议待真机 SDK 确认，拒绝猜测遥测帧")
