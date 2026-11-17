"""蜘蛛机器人协议（占位，待真机抓包确认）。

典型厂商（待确认）：Agility Robotics Digit（人形但关节多）/ 国内多足定制
需要拿到真机的
- 服务 UUID 与 写/通知 特征值 UUID
- 指令字节格式（全向移动一般支持 x/y/theta 独立轴）
- 遥测帧格式（各足受力/关节角/IMU）
确认后替换下方常量并实现 encode/decode；当前一切调用如实报错，不编造字节。
"""

from __future__ import annotations

from .base import BridgeProtocolError, ProtocolAdapter


class GenericBleSpiderV1Adapter(ProtocolAdapter):
    PROTOCOL_ID = "generic-ble-spider-v1"

    SERVICE_UUID = ""       # TODO(真机抓包)
    WRITE_CHAR_UUID = ""    # TODO(真机抓包)
    NOTIFY_CHAR_UUID = ""   # TODO(真机抓包)

    def encode_command(self, command: dict) -> bytes:
        raise BridgeProtocolError("generic-ble-spider-v1 协议待真机抓包确认，拒绝编码未知字节")

    def decode_notification(self, data: bytes) -> dict | None:
        raise BridgeProtocolError("generic-ble-spider-v1 协议待真机抓包确认，拒绝猜测遥测帧")
