"""SmartOps 通用单片机协议 v1（BLE / 串口共用）。

帧格式（多字节均为大端）::

    AA 55 | version:u8 | type:u8 | seq:u16 | length:u16 | payload | crc16:u16

- CRC16/CCITT-FALSE（poly=0x1021, init=0xFFFF）覆盖 version 到 payload，不含帧头。
- MOVE：x/y/theta 为 [-100,100] 的 int8（后端 [-1,1] 归一化量乘 100），
  speed 为 [0,100] 的 uint8，ttlMs 为 uint16；单片机超过 ttl 未续传必须停车。
- TELEMETRY：battery:u8(%)，x/y:int16(cm)，theta:int16(0.1°)，
  obstacle:u16(cm, 0xFFFF=未知)，flags:u8（bit0 急停、bit1 障碍停、bit2 低电）。
  基础帧之后可追加 0..N 个扩展块（TLV），用于形态专属遥测::

      extType:u8 | extLen:u8 | extPayload[extLen]

  - extType=0x01 WHEELS（CAR，extLen=18）：radius:u16(mm)，trackWidth:u16(mm)，
    leftSpeed/rightSpeed:int16(mm/s)，leftAngular/rightAngular:int16(0.01rad/s)，
    lidarRpm:u16，odometer:u32(cm)。
  - extType=0x02 GAIT（SPIDER，extLen=7）：legCount:u8，strideHz:u8(0.1Hz)，
    phase:u16(0.001rad)，bodyHeight:u16(mm)，contactMask:u8（bit i = Leg i 触地）。

  未知扩展按长度安全跳过（前向兼容）；已知扩展长度不符、越界或关键值非法则整帧丢弃，不猜测。
- CMD_ACK：commandSeq:u16，status:u8，reason:u8。
- EVENT：kind:u8，value:u8。

本协议是 SmartOps 侧明确约定的可烧写固件协议，不冒充任何厂商私有协议。
"""

from __future__ import annotations

import math
import struct

from .base import BridgeProtocolError, ProtocolAdapter

_SOF = b"\xAA\x55"
_VERSION = 1
_MAX_PAYLOAD = 512
_TELEMETRY = struct.Struct(">BhhhHB")
_ACK = struct.Struct(">HBB")
_EVENT = struct.Struct(">BB")
_HELLO = struct.Struct(">HH")
_MOVE = struct.Struct(">bbbBH")
_WHEELS = struct.Struct(">HHhhhhHI")
_GAIT = struct.Struct(">BBHHB")

_ACK_STATUS = {0: "OK", 1: "INVALID", 2: "BUSY", 3: "EXPIRED", 4: "FAILED"}
_EVENT_KIND = {
    1: "ARRIVED",
    2: "OBSTACLE_STOP",
    3: "FAULT",
    4: "LOW_BATTERY",
    5: "STOPPED",
}


def crc16_ccitt(data: bytes) -> int:
    """CRC16/CCITT-FALSE；标准校验串 ``123456789`` 的结果应为 0x29B1。"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


class GenericMcuV1Adapter(ProtocolAdapter):
    PROTOCOL_ID = "generic-mcu-v1"

    TYPE_HELLO = 0x01
    TYPE_HELLO_ACK = 0x02
    TYPE_MOVE = 0x10
    TYPE_STOP = 0x11
    TYPE_TELEMETRY = 0x20
    TYPE_CMD_ACK = 0x30
    TYPE_EVENT = 0x31

    CAP_MOVE = 0x01
    CAP_TELEMETRY = 0x02
    CAP_ACK = 0x04

    # TELEMETRY 扩展块类型
    EXT_WHEELS = 0x01
    EXT_GAIT = 0x02

    def __init__(self, service_uuid: str = "", write_char_uuid: str = "", notify_char_uuid: str = ""):
        # 自定义 BLE 服务 UUID 由部署方按固件配置显式提供；串口模式无需填写。
        self.SERVICE_UUID = service_uuid.strip()
        self.WRITE_CHAR_UUID = write_char_uuid.strip()
        self.NOTIFY_CHAR_UUID = notify_char_uuid.strip()
        self._buffer = bytearray()
        self._sequence = 0
        self._pending: dict[int, str] = {}

    def reset(self) -> None:
        # 序号保持单调，避免重连后旧 ACK 被误认为新命令；半包和待确认命令不跨会话继承。
        self._buffer.clear()
        self._pending.clear()

    def _next_sequence(self) -> int:
        self._sequence = (self._sequence + 1) & 0xFFFF
        if self._sequence == 0:
            self._sequence = 1
        return self._sequence

    def _frame(self, frame_type: int, sequence: int, payload: bytes = b"") -> bytes:
        body = bytes((_VERSION, frame_type)) + struct.pack(">HH", sequence, len(payload)) + payload
        return _SOF + body + struct.pack(">H", crc16_ccitt(body))

    def encode_hello(self) -> bytes:
        capabilities = self.CAP_MOVE | self.CAP_TELEMETRY | self.CAP_ACK
        return self._frame(self.TYPE_HELLO, self._next_sequence(), _HELLO.pack(_VERSION, capabilities))

    def encode_command(self, command: dict) -> bytes:
        op = str(command.get("op", "")).strip().upper()
        params = command.get("params") or {}
        sequence = self._next_sequence()
        if op == "STOP":
            frame_type, payload = self.TYPE_STOP, b""
        elif op == "MOVE":
            frame_type = self.TYPE_MOVE
            payload = _MOVE.pack(
                self._scaled(params.get("x", 0), 100, -1, 1, "x"),
                self._scaled(params.get("y", 0), 100, -1, 1, "y"),
                self._scaled(params.get("theta", 0), 100, -1, 1, "theta"),
                self._scaled(params.get("speed", 0), 100, 0, 1, "speed"),
                self._integer(params.get("ttlMs", 200), 50, 500, "ttlMs"),
            )
        else:
            raise BridgeProtocolError(f"generic-mcu-v1 P0 仅支持 MOVE/STOP，拒绝编码 {op or '空命令'}")
        self._pending[sequence] = op
        return self._frame(frame_type, sequence, payload)

    @staticmethod
    def _number(value, name: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise BridgeProtocolError(f"{name} 不是数值") from error
        if not math.isfinite(number):
            raise BridgeProtocolError(f"{name} 不是有限数值")
        return number

    def _scaled(self, value, scale: int, minimum: float, maximum: float, name: str) -> int:
        number = self._number(value, name)
        if number < minimum or number > maximum:
            raise BridgeProtocolError(f"{name} 必须在 {minimum}~{maximum} 之间")
        return int(round(number * scale))

    def _integer(self, value, minimum: int, maximum: int, name: str) -> int:
        number = self._number(value, name)
        result = int(number)
        if number != result or result < minimum or result > maximum:
            raise BridgeProtocolError(f"{name} 必须是 {minimum}~{maximum} 的整数")
        return result

    def feed(self, data: bytes) -> list[dict]:
        """喂入任意长度的传输数据，返回完整且 CRC 正确的消息；支持半包与粘包。"""
        self._buffer.extend(data)
        messages: list[dict] = []
        while True:
            start = self._buffer.find(_SOF)
            if start < 0:
                # 保留末尾可能的半个帧头 0xAA，其余噪声丢弃。
                trailing = 1 if self._buffer.endswith(b"\xAA") else 0
                del self._buffer[:len(self._buffer) - trailing]
                break
            if start:
                del self._buffer[:start]
            if len(self._buffer) < 10:
                break
            length = struct.unpack_from(">H", self._buffer, 6)[0]
            if length > _MAX_PAYLOAD:
                del self._buffer[:2]
                continue
            total = length + 10
            if len(self._buffer) < total:
                break
            raw = bytes(self._buffer[:total])
            del self._buffer[:total]
            if raw[2] != _VERSION or struct.unpack(">H", raw[-2:])[0] != crc16_ccitt(raw[2:-2]):
                continue
            message = self._decode_frame(raw[3], struct.unpack_from(">H", raw, 4)[0], raw[8:-2])
            if message is not None:
                messages.append(message)
        return messages

    def _decode_telemetry_extensions(self, data: bytes, telemetry: dict) -> bool:
        """解析 TELEMETRY 尾部 TLV 扩展块；结构非法返回 False（整帧丢弃）。

        未知 extType 按 extLen 安全跳过，便于固件后续增加新块而不影响旧桥。
        """
        offset = 0
        while offset < len(data):
            if offset + 2 > len(data):
                return False
            ext_type = data[offset]
            ext_len = data[offset + 1]
            start = offset + 2
            end = start + ext_len
            if end > len(data):
                return False
            body = data[start:end]
            if ext_type == self.EXT_WHEELS:
                if ext_len != _WHEELS.size:
                    return False
                radius, track, left, right, left_ang, right_ang, rpm, odometer = _WHEELS.unpack(body)
                # 轮径/轮距为 0 说明固件未标定，不输出不可信轮速
                if radius > 0 and track > 0:
                    telemetry["wheels"] = {
                        "radius": round(radius / 1000, 3),
                        "trackWidth": round(track / 1000, 3),
                        "leftSpeed": round(left / 1000, 3),
                        "rightSpeed": round(right / 1000, 3),
                        "leftAngular": round(left_ang / 100, 2),
                        "rightAngular": round(right_ang / 100, 2),
                        "lidarRpm": rpm,
                    }
                    telemetry["odometer"] = round(odometer / 100, 2)
            elif ext_type == self.EXT_GAIT:
                if ext_len != _GAIT.size:
                    return False
                leg_count, stride, phase, height, contact_mask = _GAIT.unpack(body)
                if not 1 <= leg_count <= 8:
                    return False
                telemetry["gait"] = {
                    "legCount": leg_count,
                    "strideHz": round(stride / 10, 1),
                    "phase": round(phase / 1000, 3),
                    "footContacts": [bool(contact_mask >> i & 0x01) for i in range(leg_count)],
                    "bodyHeight": round(height / 1000, 3),
                }
            offset = end
        return True

    def _decode_frame(self, frame_type: int, sequence: int, payload: bytes) -> dict | None:
        try:
            if frame_type == self.TYPE_TELEMETRY and len(payload) >= _TELEMETRY.size:
                battery, x, y, theta, obstacle, flags = _TELEMETRY.unpack_from(payload)
                if battery > 100:
                    return None
                telemetry = {
                    "battery": battery / 100,
                    "pose": {"x": x / 100, "y": y / 100, "theta": theta / 10},
                    "simulated": False,
                }
                if obstacle != 0xFFFF:
                    telemetry["obstacleDistance"] = obstacle / 100
                if flags & 0x01:
                    telemetry["estop"] = True
                if flags & 0x02:
                    telemetry["obstacleStopped"] = True
                if flags & 0x04:
                    telemetry["lowBattery"] = True
                if not self._decode_telemetry_extensions(payload[_TELEMETRY.size:], telemetry):
                    return None
                return {"channel": "telemetry", "payload": telemetry}

            if frame_type == self.TYPE_CMD_ACK and len(payload) == _ACK.size:
                command_seq, status, reason = _ACK.unpack(payload)
                return {"channel": "ack", "payload": {
                    "commandSeq": command_seq,
                    "op": self._pending.pop(command_seq, ""),
                    "status": _ACK_STATUS.get(status, "UNKNOWN"),
                    "statusCode": status,
                    "reasonCode": reason,
                }}

            if frame_type == self.TYPE_EVENT and len(payload) == _EVENT.size:
                kind, value = _EVENT.unpack(payload)
                return {"channel": "event", "payload": {
                    "kind": _EVENT_KIND.get(kind, "UNKNOWN"),
                    "kindCode": kind,
                    "value": value,
                }}

            if frame_type == self.TYPE_HELLO_ACK and len(payload) == _HELLO.size:
                version, capabilities = _HELLO.unpack(payload)
                return {"channel": "event", "payload": {
                    "kind": "DEVICE_HELLO",
                    "protocolVersion": version,
                    "capabilities": capabilities,
                }}
        except struct.error:
            return None
        return None

    def decode_notification(self, data: bytes) -> dict | None:
        """兼容基类单包接口；桥实现使用 feed()，避免 ACK/事件被吞掉。"""
        for message in self.feed(data):
            if message["channel"] == "telemetry":
                return message["payload"]
        return None
