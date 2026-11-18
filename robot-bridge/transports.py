"""真机传输层：BLE 与串口统一为异步 connect/read/write/close。"""

from __future__ import annotations

import asyncio
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

        # 每次连接使用独立队列，旧连接的断开/通知回调不会污染重连后的会话。
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
        # pyserial 超时会返回空 bytes；空读只是暂无数据，持续等待，只有关闭才返回空给上层。
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
