"""真机传输层：BLE / 串口 / UDP 统一为异步 connect/read/write/close。"""

from __future__ import annotations

import asyncio
import socket
from abc import ABC, abstractmethod


class BridgeTransportError(Exception):
    """设备传输不可用；桥据此收拢连接并进入重连。"""


class McuTransport(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def read(self) -> bytes:
        """读取下一段字节；返回空 bytes 表示连接已关闭。"""

    @abstractmethod
    async def write(self, data: bytes) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass


class BleTransport(McuTransport):
    def __init__(self, address: str, service_uuid: str, write_char_uuid: str, notify_char_uuid: str):
        self.address = address
        self.service_uuid = service_uuid
        self.write_char_uuid = write_char_uuid
        self.notify_char_uuid = notify_char_uuid
        self._client = None
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def connect(self) -> None:
        if not all((self.address, self.service_uuid, self.write_char_uuid, self.notify_char_uuid)):
            raise BridgeTransportError("BLE 模式必须提供 MAC、服务 UUID、写特征值 UUID、通知特征值 UUID")
        try:
            from bleak import BleakClient
        except ImportError as error:
            raise BridgeTransportError("缺少 bleak：请先执行 pip install -r requirements.txt") from error

        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._queue = queue
        client = BleakClient(self.address, disconnected_callback=lambda _client: queue.put_nowait(None))
        self._client = client
        try:
            await client.connect()
            await client.start_notify(
                self.notify_char_uuid,
                lambda _characteristic, data: queue.put_nowait(bytes(data)),
            )
        except Exception as error:
            self._client = None
            try:
                await client.disconnect()
            except Exception:
                pass
            raise BridgeTransportError(f"BLE 连接或订阅失败：{error}") from error
        print(f"[bridge] BLE 已连接 {self.address}，已订阅 {self.notify_char_uuid}")

    async def read(self) -> bytes:
        data = await self._queue.get()
        return data or b""

    async def write(self, data: bytes) -> None:
        client = self._client
        if client is None or not client.is_connected:
            raise BridgeTransportError("BLE 未连接，拒绝写入")
        try:
            await client.write_gatt_char(self.write_char_uuid, data, response=True)
        except Exception as error:
            raise BridgeTransportError(f"BLE 指令写入失败：{error}") from error

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.stop_notify(self.notify_char_uuid)
        except Exception:
            pass
        try:
            await client.disconnect()
        except Exception:
            pass


class SerialTransport(McuTransport):
    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self._serial = None
        self._closing = False

    async def connect(self) -> None:
        if not self.port:
            raise BridgeTransportError("串口模式必须提供 --port")
        try:
            import serial
        except ImportError as error:
            raise BridgeTransportError("缺少 pyserial：请先执行 pip install -r requirements.txt") from error
        self._closing = False
        try:
            self._serial = await asyncio.to_thread(
                lambda: serial.Serial(port=self.port, baudrate=self.baudrate, timeout=0.2, write_timeout=2)
            )
        except Exception as error:
            raise BridgeTransportError(f"串口打开失败：{error}") from error
        print(f"[bridge] 串口已打开 {self.port} @ {self.baudrate}")

    async def read(self) -> bytes:
        while True:
            port = self._serial
            if port is None:
                return b""
            try:
                data = await asyncio.to_thread(port.read, 4096)
            except Exception as error:
                if self._closing:
                    return b""
                raise BridgeTransportError(f"串口读取失败：{error}") from error
            if data:
                return bytes(data)

    async def write(self, data: bytes) -> None:
        port = self._serial
        if port is None:
            raise BridgeTransportError("串口未连接，拒绝写入")
        try:
            written = await asyncio.to_thread(port.write, data)
        except Exception as error:
            raise BridgeTransportError(f"串口指令写入失败：{error}") from error
        if written != len(data):
            raise BridgeTransportError(f"串口只写入 {written}/{len(data)} 字节")

    async def close(self) -> None:
        self._closing = True
        port, self._serial = self._serial, None
        if port is not None:
            try:
                await asyncio.to_thread(port.close)
            except Exception:
                pass


class UdpTransport(McuTransport):
    """面向宇树 unitree_legged_sdk 旧协议（默认 8000 端口）的 UDP 传输层。

    Go2 出厂固件同时支持 DDS (8080) 和旧 UDP (8000) 两种协议，本传输层订阅后者；
    协议编解码由 unitree_protocol.py 独立负责（LowState / MotorState packed(1) struct）。
    G1 人形仅支持 unitree_sdk2 (DDS) 协议，不走本传输层。
    """

    def __init__(self, bind_ip: str = "0.0.0.0", bind_port: int = 8000,
                 robot_ip: str = "192.168.123.161", robot_port: int = 8000):
        self.bind_ip = bind_ip
        self.bind_port = bind_port
        self.robot_ip = robot_ip
        self.robot_port = robot_port
        self._sock: socket.socket | None = None
        self._closing = False
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        self._loop = loop
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.bind_ip, self.bind_port))
            sock.setblocking(False)
        except OSError as error:
            raise BridgeTransportError(
                f"UDP 绑定 {self.bind_ip}:{self.bind_port} 失败：{error}"
            ) from error
        self._sock = sock
        print(f"[bridge] UDP 已绑定 {self.bind_ip}:{self.bind_port}，机器人目标 {self.robot_ip}:{self.robot_port}")

    async def read(self) -> bytes:
        sock, loop = self._sock, self._loop
        if sock is None or loop is None:
            return b""
        while not self._closing:
            try:
                data, _addr = await loop.sock_recvfrom(sock, 4096)
                return bytes(data)
            except (BlockingIOError, InterruptedError):
                await asyncio.sleep(0.001)
            except OSError:
                if self._closing:
                    return b""
                raise
        return b""

    async def write(self, data: bytes) -> None:
        sock, loop = self._sock, self._loop
        if sock is None or loop is None:
            raise BridgeTransportError("UDP 未连接，拒绝写入")
        if not (self.robot_ip and self.robot_port):
            raise BridgeTransportError("未指定机器人 IP/端口，无法发送命令")
        await loop.sock_sendto(sock, data, (self.robot_ip, self.robot_port))

    async def close(self) -> None:
        self._closing = True
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
