"""四足机器狗协议（占位，待真机抓包确认）。

典型厂商（待确认）：宇树 Unitree / 宇树 Go / 小米 CyberOne mini
需要拿到真机的
- 服务 UUID 与 写/通知 特征值 UUID
- 指令字节格式（四足通常走厂商 SDK 或 高频 JSON websocket，不走裸 BLE 字节）
- 遥测帧格式（关节角/足底触地/IMU）
确认后替换下方常量并实现 encode/decode；当前一切调用如实报错，不编造字节。
"""

from __future__ import annotations

from .base import BridgeProtocolError, ProtocolAdapter


class GenericBleDogV1Adapter(ProtocolAdapter):
    PROTOCOL_ID = "generic-ble-dog-v1"

    SERVICE_UUID = ""       # TODO(真机抓包) 或厂商 SDK 进程 URL
    WRITE_CHAR_UUID = ""    # TODO(真机抓包)
    NOTIFY_CHAR_UUID = ""   # TODO(真机抓包)

    def encode_command(self, command: dict) -> bytes:
        raise BridgeProtocolError("generic-ble-dog-v1 协议待真机 SDK 确认，拒绝编码未知字节")

    def decode_notification(self, data: bytes) -> dict | None:
        raise BridgeProtocolError("generic-ble-dog-v1 协议待真机 SDK 确认，拒绝猜测遥测帧")
