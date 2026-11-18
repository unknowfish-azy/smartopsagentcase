from __future__ import annotations

import struct
import unittest

from protocols.base import BridgeProtocolError
from protocols.generic_mcu_v1 import GenericMcuV1Adapter, crc16_ccitt


def make_frame(frame_type: int, sequence: int, payload: bytes = b"", version: int = 1) -> bytes:
    body = bytes((version, frame_type)) + struct.pack(">HH", sequence, len(payload)) + payload
    return b"\xAA\x55" + body + struct.pack(">H", crc16_ccitt(body))


class GenericMcuV1Test(unittest.TestCase):
    def setUp(self):
        self.adapter = GenericMcuV1Adapter()

    def test_crc_standard_vector(self):
        self.assertEqual(crc16_ccitt(b"123456789"), 0x29B1)

    def test_encode_move_uses_fixed_point_and_ttl(self):
        raw = self.adapter.encode_command({"op": "MOVE", "params": {
            "x": 0.5, "y": -0.25, "theta": 1, "speed": 0.4, "ttlMs": 200,
        }})
        self.assertEqual(raw[:4], b"\xAA\x55\x01\x10")
        self.assertEqual(struct.unpack_from(">H", raw, 4)[0], 1)
        self.assertEqual(raw[8:-2], struct.pack(">bbbBH", 50, -25, 100, 40, 200))
        self.assertEqual(struct.unpack(">H", raw[-2:])[0], crc16_ccitt(raw[2:-2]))

    def test_encode_stop_has_empty_payload(self):
        raw = self.adapter.encode_command({"op": "STOP", "params": {}})
        self.assertEqual(raw[3], self.adapter.TYPE_STOP)
        self.assertEqual(struct.unpack_from(">H", raw, 6)[0], 0)

    def test_rejects_unknown_command_and_out_of_range_motion(self):
        with self.assertRaises(BridgeProtocolError):
            self.adapter.encode_command({"op": "PATROL", "params": {}})
        with self.assertRaises(BridgeProtocolError):
            self.adapter.encode_command({"op": "MOVE", "params": {"x": 2}})
        with self.assertRaises(BridgeProtocolError):
            self.adapter.encode_command({"op": "MOVE", "params": {"ttlMs": 501}})

    def test_feed_supports_half_packet_and_sticky_packets(self):
        move = self.adapter.encode_command({"op": "MOVE", "params": {"x": 0.1}})
        command_seq = struct.unpack_from(">H", move, 4)[0]
        telemetry = make_frame(self.adapter.TYPE_TELEMETRY, 9,
                               struct.pack(">BhhhHB", 82, 120, -340, 900, 45, 0))
        ack = make_frame(self.adapter.TYPE_CMD_ACK, 10, struct.pack(">HBB", command_seq, 0, 0))

        self.assertEqual(self.adapter.feed(telemetry[:5]), [])
        messages = self.adapter.feed(telemetry[5:] + ack)
        self.assertEqual([item["channel"] for item in messages], ["telemetry", "ack"])
        self.assertEqual(messages[0]["payload"], {
            "battery": 0.82,
            "pose": {"x": 1.2, "y": -3.4, "theta": 90.0},
            "obstacleDistance": 0.45,
            "simulated": False,
        })
        self.assertEqual(messages[1]["payload"]["op"], "MOVE")
        self.assertEqual(messages[1]["payload"]["status"], "OK")

    def test_feed_supports_split_frame_header(self):
        raw = make_frame(self.adapter.TYPE_EVENT, 3, struct.pack(">BB", 2, 1))
        self.assertEqual(self.adapter.feed(b"\xAA"), [])
        messages = self.adapter.feed(raw[1:])
        self.assertEqual(messages[0]["payload"]["kind"], "OBSTACLE_STOP")

    def test_bad_crc_and_bad_battery_are_not_reported(self):
        telemetry = make_frame(self.adapter.TYPE_TELEMETRY, 1,
                               struct.pack(">BhhhHB", 82, 0, 0, 0, 0xFFFF, 0))
        corrupted = telemetry[:-1] + bytes((telemetry[-1] ^ 0xFF,))
        self.assertEqual(self.adapter.feed(corrupted), [])
        bad_battery = make_frame(self.adapter.TYPE_TELEMETRY, 2,
                                 struct.pack(">BhhhHB", 101, 0, 0, 0, 0, 0))
        self.assertEqual(self.adapter.feed(bad_battery), [])

    def test_unknown_obstacle_and_flags(self):
        raw = make_frame(self.adapter.TYPE_TELEMETRY, 1,
                         struct.pack(">BhhhHB", 15, 0, 0, 0, 0xFFFF, 0x07))
        message = self.adapter.feed(raw)[0]["payload"]
        self.assertNotIn("obstacleDistance", message)
        self.assertTrue(message["estop"])
        self.assertTrue(message["obstacleStopped"])
        self.assertTrue(message["lowBattery"])


if __name__ == "__main__":
    unittest.main()
