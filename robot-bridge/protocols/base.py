"""协议适配器基类。

每个真机形态/厂商对应一个 ProtocolAdapter 实现：
- 常量：PROTOCOL_ID / SERVICE_UUID / WRITE_CHAR_UUID / NOTIFY_CHAR_UUID（真机抓包后回填）
- encode_command：把统一命令信封（{"op":"MOVE","params":{...}}）编码为特征值字节
- decode_notification：把 BLE notify 原始字节解码为遥测/事件 dict（解析失败返回 None，不猜测）
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BridgeProtocolError(Exception):
    """协议未就绪或编解码失败；桥侧据此上报 FAULT，绝不猜测字节含义。"""


class ProtocolAdapter(ABC):
    PROTOCOL_ID: str = ""
    SERVICE_UUID: str = ""
    WRITE_CHAR_UUID: str = ""
    NOTIFY_CHAR_UUID: str = ""

    @abstractmethod
    def encode_command(self, command: dict) -> bytes:
        """统一命令 → 设备特征值字节。未知 op 抛 BridgeProtocolError。"""

    @abstractmethod
    def decode_notification(self, data: bytes) -> dict | None:
        """设备 notify 原始字节 → 遥测/事件 dict；无法解析返回 None。"""
