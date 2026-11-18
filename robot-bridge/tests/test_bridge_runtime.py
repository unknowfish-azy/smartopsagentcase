from __future__ import annotations

import asyncio
import io
import json
import os
import struct
import sys
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch

import bridge
from protocols.base import BridgeProtocolError
from protocols.generic_mcu_v1 import GenericMcuV1Adapter, crc16_ccitt
from transports import BridgeTransportError


def make_frame(frame_type: int, sequence: int, payload: bytes = b"", version: int = 1) -> bytes:
    body = bytes((version, frame_type)) + struct.pack(">HH", sequence, len(payload)) + payload
    return b"\xAA\x55" + body + struct.pack(">H", crc16_ccitt(body))


def hello_ack(capabilities: int = 0x07, version: int = 1) -> bytes:
    return make_frame(GenericMcuV1Adapter.TYPE_HELLO_ACK, 1, struct.pack(">HH", version, capabilities))


class FakeSocket:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self.sent: list[dict] = []
        self.close_code = 1000

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


class FakeSocketContext:
    def __init__(self, socket: FakeSocket):
        self.socket = socket

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeTransport:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.writes: list[bytes] = []
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def read(self) -> bytes:
        await asyncio.sleep(0)
        return self.chunks.pop(0) if self.chunks else b""

    async def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def close(self) -> None:
        self.connected = False


class BlockingTransport(FakeTransport):
    async def read(self) -> bytes:
        await asyncio.Event().wait()
        return b""


def run_args(transport: str) -> SimpleNamespace:
    return SimpleNamespace(
        backend="http://127.0.0.1:8080",
        device="robot-car-01",
        form_factor="CAR",
        protocol="generic-mcu-v1",
        transport=transport,
        mac="",
        service_uuid="",
        write_char_uuid="",
        notify_char_uuid="",
        port="",
        baud=115200,
    )


class BridgeRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.adapter = GenericMcuV1Adapter()

    async def test_command_pump_writes_move_and_stop(self):
        socket = FakeSocket([
            json.dumps({"type": "cmd", "payload": {
                "op": "MOVE", "params": {"x": 0.5, "speed": 0.4, "ttlMs": 200},
            }}),
            json.dumps({"type": "cmd", "payload": {"op": "STOP", "params": {}}}),
        ])
        transport = FakeTransport()

        await bridge._command_pump(socket, transport, self.adapter, "robot-car-01")

        self.assertEqual(len(transport.writes), 2)
        self.assertEqual(transport.writes[0][3], self.adapter.TYPE_MOVE)
        self.assertEqual(transport.writes[1][3], self.adapter.TYPE_STOP)
        self.assertEqual(socket.sent, [])

    async def test_command_pump_rejects_unknown_command_without_writing(self):
        socket = FakeSocket([
            json.dumps({"type": "cmd", "payload": {"op": "PATROL", "params": {}}}),
        ])
        transport = FakeTransport()

        await bridge._command_pump(socket, transport, self.adapter, "robot-car-01")

        self.assertEqual(transport.writes, [])
        self.assertEqual(len(socket.sent), 1)
        self.assertEqual(socket.sent[0]["type"], "event")
        self.assertEqual(socket.sent[0]["payload"]["kind"], "COMMAND_REJECTED")
        self.assertEqual(socket.sent[0]["payload"]["deviceKey"], "robot-car-01")
        self.assertEqual(socket.sent[0]["payload"]["op"], "PATROL")

    async def test_wait_device_hello_preserves_messages_received_during_handshake(self):
        telemetry = make_frame(
            self.adapter.TYPE_TELEMETRY,
            2,
            struct.pack(">BhhhHB", 80, 100, -200, 450, 0xFFFF, 0),
        )
        transport = FakeTransport([telemetry + hello_ack()])

        messages = await bridge._wait_device_hello(transport, self.adapter)

        self.assertEqual([item["channel"] for item in messages], ["telemetry", "event"])
        self.assertEqual(messages[1]["payload"]["kind"], "DEVICE_HELLO")

    async def test_wait_device_hello_rejects_bad_version_and_missing_capabilities(self):
        cases = (
            hello_ack(version=2),
            hello_ack(capabilities=self.adapter.CAP_MOVE),
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(BridgeProtocolError):
                    await bridge._wait_device_hello(FakeTransport([raw]), GenericMcuV1Adapter())

    async def test_wait_device_hello_can_time_out(self):
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(
                bridge._wait_device_hello(BlockingTransport(), self.adapter),
                timeout=0.01,
            )

    async def test_device_pump_forwards_telemetry_event_and_ack_then_reports_disconnect(self):
        command = self.adapter.encode_command({"op": "MOVE", "params": {"x": 0.2}})
        command_seq = struct.unpack_from(">H", command, 4)[0]
        telemetry = make_frame(
            self.adapter.TYPE_TELEMETRY,
            2,
            struct.pack(">BhhhHB", 75, 0, 0, 0, 30, 0),
        )
        event = make_frame(self.adapter.TYPE_EVENT, 3, struct.pack(">BB", 2, 1))
        ack = make_frame(self.adapter.TYPE_CMD_ACK, 4, struct.pack(">HBB", command_seq, 0, 0))
        socket = FakeSocket()

        with self.assertRaises(BridgeTransportError):
            await bridge._device_pump(
                socket,
                FakeTransport([telemetry + event + ack]),
                self.adapter,
                "robot-car-01",
            )

        self.assertEqual([item["type"] for item in socket.sent], ["telemetry", "event", "bridge_ack"])
        for message in socket.sent:
            self.assertEqual(message["payload"]["deviceKey"], "robot-car-01")
            self.assertEqual(message["payload"]["protocolId"], "generic-mcu-v1")
        self.assertFalse(socket.sent[0]["payload"]["simulated"])
        self.assertEqual(socket.sent[1]["payload"]["kind"], "OBSTACLE_STOP")
        self.assertEqual(socket.sent[2]["payload"]["op"], "MOVE")
        self.assertEqual(socket.sent[2]["payload"]["status"], "OK")

    async def test_run_session_announces_device_only_after_real_hello_ack(self):
        socket = FakeSocket()
        transport = FakeTransport([hello_ack()])
        fake_websockets = SimpleNamespace(connect=lambda *args, **kwargs: FakeSocketContext(socket))

        with patch.dict(sys.modules, {"websockets": fake_websockets}):
            with self.assertRaises(BridgeTransportError):
                await bridge._run_session(run_args("serial"), self.adapter, transport, "http://backend", "token")

        self.assertEqual(len(transport.writes), 1)
        self.assertEqual(transport.writes[0][3], self.adapter.TYPE_HELLO)
        self.assertEqual(socket.sent[0]["type"], "bridge_hello")
        self.assertFalse(socket.sent[0]["payload"]["simulated"])
        self.assertEqual(socket.sent[0]["payload"]["deviceKeys"], ["robot-car-01"])

    async def test_run_session_does_not_announce_device_without_hello_ack(self):
        socket = FakeSocket()
        transport = FakeTransport()
        fake_websockets = SimpleNamespace(connect=lambda *args, **kwargs: FakeSocketContext(socket))

        with patch.dict(sys.modules, {"websockets": fake_websockets}):
            with self.assertRaises(BridgeTransportError):
                await bridge._run_session(run_args("serial"), self.adapter, transport, "http://backend", "token")

        self.assertEqual(socket.sent, [])

    async def test_run_forever_reconnects_after_failure_but_stops_on_fatal_error(self):
        from unittest.mock import AsyncMock

        transport = FakeTransport()
        with (
            patch.object(
                bridge,
                "_run_session",
                new=AsyncMock(side_effect=[BridgeTransportError("断开"), bridge.BridgeFatalError("鉴权失败")]),
            ) as session,
            patch.object(bridge.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            result = await bridge._run_forever(
                run_args("serial"), self.adapter, transport, "http://backend", "token"
            )

        self.assertEqual(result, 1)
        self.assertEqual(session.await_count, 2)
        sleep.assert_awaited_once_with(1)
        self.assertFalse(transport.connected)


class BridgeCliTest(unittest.TestCase):
    def test_run_fails_closed_without_token(self):
        with patch.dict(os.environ, {bridge.TOKEN_ENV: ""}):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(bridge.run(run_args("serial")), 2)

    def test_run_rejects_missing_transport_parameters(self):
        with patch.dict(os.environ, {bridge.TOKEN_ENV: "test-token"}):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(bridge.run(run_args("ble")), 2)
                self.assertEqual(bridge.run(run_args("serial")), 2)


if __name__ == "__main__":
    unittest.main()
