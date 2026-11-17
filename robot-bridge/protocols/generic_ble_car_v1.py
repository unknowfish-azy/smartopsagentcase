"""巡检车通用协议（占位，待真机抓包确认）。

详细设计第 7 节待确认项 #1：需要拿到真机的
- 服务 UUID 与 写/通知 特征值 UUID
- 指令字节格式（如 {'M',x_int8,y_int8,theta_int8,speed_uint8}）
- 遥测帧格式（电量/位姿/障碍距离）
确认后替换下方常量并实现 encode/decode；当前一切调用如实报错，不编造字节。
"""

from __future__ import annotations

from .base import BridgeProtocolError, ProtocolAdapter


class GenericBleCarV1Adapter(ProtocolAdapter):
    PROTOCOL_ID = "generic-ble-car-v1"

    SERVICE_UUID = ""       # TODO(真机抓包)
    WRITE_CHAR_UUID = ""    # TODO(真机抓包)
    NOTIFY_CHAR_UUID = ""   # TODO(真机抓包)

    def encode_command(self, command: dict) -> bytes:
        raise BridgeProtocolError("generic-ble-car-v1 协议待真机抓包确认，拒绝编码未知字节")

    def decode_notification(self, data: bytes) -> dict | None:
        raise BridgeProtocolError("generic-ble-car-v1 协议待真机抓包确认，拒绝猜测遥测帧")
