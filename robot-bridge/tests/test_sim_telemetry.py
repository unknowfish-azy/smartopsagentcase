"""巡检车 / 蜘蛛机器人独立遥测模拟测试。

覆盖：
  - CAR：差速轮速（直行等速、转向内外轮差速）、轮半径/轮距/LiDAR 转速、里程；
  - SPIDER：8 足 16 关节（与 spider-bot.rig.json 同名同 home）、交替步态、站立归零；
  - 形态独立遥测字段：CAR 有 wheels/odometer 无 joints，SPIDER 有 joints/gait 无 wheels，
    DOG/ROBOT 既有字段不变。
"""

from __future__ import annotations

import json
import math
import time
import unittest
from pathlib import Path

from gait_solver import spider_gait, spider_joints
from sim import SimulatedDevice, car_wheel_speeds

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIDER_RIG = REPO_ROOT / "frontend/public/models/robot/spider-bot.rig.json"


def load_spider_rig() -> dict:
    return json.loads(SPIDER_RIG.read_text(encoding="utf-8"))


class SpiderJointsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.meta = load_spider_rig()
        self.knee_home = self.meta["joints"]["Leg0_knee"]["home"]

    def test_stand_returns_home_and_all_16_joints(self):
        joints = spider_joints(0.0, 0.0, 0.0, 12.3)
        self.assertEqual(len(joints), 16)
        for i in range(8):
            self.assertAlmostEqual(joints[f"Leg{i}_hip"], 0.0, places=6)
            self.assertAlmostEqual(joints[f"Leg{i}_knee"], self.knee_home, places=6)

    def test_joint_names_and_home_match_rig_json(self):
        joints = spider_joints(0.4, 0.0, 0.0, 0.1)
        self.assertEqual(set(joints), set(self.meta["joints"]))
        for name, value in joints.items():
            meta = self.meta["joints"][name]
            self.assertGreaterEqual(value, meta["range"][0] - 1e-6, name)
            self.assertLessEqual(value, meta["range"][1] + 1e-6, name)

    def test_walk_alternates_leg_groups_and_clamps_amplitude(self):
        joints = spider_joints(0.4, 0.0, 0.0, 0.1)
        self.assertNotAlmostEqual(joints["Leg0_hip"], joints["Leg1_hip"], places=3)
        # 摆动相才抬腿：knee 不小于站立 home
        self.assertGreater(joints["Leg0_knee"], self.knee_home)
        fast = spider_joints(1.0, 0.0, 0.0, 0.1)
        self.assertLessEqual(abs(fast["Leg0_hip"]), 0.28 + 1e-6)
        self.assertLessEqual(fast["Leg0_knee"] - self.knee_home, 0.34 + 1e-6)

    def test_lateral_only_drive_still_steps(self):
        """全向蜘蛛只看横移也应起步（CAR 不适用）。"""
        joints = spider_joints(0.0, 0.4, 0.0, 0.1)
        self.assertNotAlmostEqual(joints["Leg0_hip"], 0.0, places=3)

    def test_gait_metrics_contacts_half_stance(self):
        gait = spider_gait(0.4, 0.0, 0.0, 0.1)
        self.assertEqual(gait["legCount"], 8)
        self.assertEqual(len(gait["footContacts"]), 8)
        self.assertGreater(gait["strideHz"], 0)
        self.assertTrue(any(gait["footContacts"]))
        self.assertTrue(any(not c for c in gait["footContacts"]))
        self.assertGreaterEqual(gait["bodyHeight"], 0.29)

        stand = spider_gait(0.0, 0.0, 0.0, 0.1)
        self.assertEqual(stand["strideHz"], 0)
        self.assertTrue(all(stand["footContacts"]))
        self.assertAlmostEqual(stand["bodyHeight"], 0.29, places=3)


class CarWheelTelemetryTest(unittest.TestCase):
    def test_straight_line_left_right_equal(self):
        wheels = car_wheel_speeds(0.4, 0.0)
        self.assertAlmostEqual(wheels["leftSpeed"], 0.4, places=3)
        self.assertAlmostEqual(wheels["rightSpeed"], 0.4, places=3)
        self.assertEqual(wheels["radius"], 0.075)
        self.assertEqual(wheels["trackWidth"], 0.32)
        self.assertEqual(wheels["lidarRpm"], 600)

    def test_turning_is_differential(self):
        left_turn = car_wheel_speeds(0.4, 0.5)
        self.assertLess(left_turn["leftSpeed"], left_turn["rightSpeed"])
        omega = math.radians(30.0)
        self.assertAlmostEqual(left_turn["rightSpeed"] - left_turn["leftSpeed"], omega * 0.32, places=2)

        right_turn = car_wheel_speeds(0.4, -0.5)
        self.assertGreater(right_turn["leftSpeed"], right_turn["rightSpeed"])

    def test_standstill_wheels_zero_and_odometer(self):
        wheels = car_wheel_speeds(0.0, 0.0)
        self.assertEqual(wheels["leftAngular"], 0)
        self.assertEqual(wheels["rightAngular"], 0)

        car = SimulatedDevice("robot-car-01", "CAR")
        car.linear = 0.4
        car.last_command_at = time.monotonic()
        car.last_tick = time.monotonic() - 0.2
        car.tick()
        self.assertGreater(car.odometer, 0)

        car.apply("STOP", {})
        payload = car.telemetry()
        self.assertEqual(payload["wheels"]["leftSpeed"], 0)
        self.assertEqual(payload["wheels"]["rightSpeed"], 0)


class FormTelemetryTest(unittest.TestCase):
    def test_car_payload_has_wheels_and_odometer_but_no_joints(self):
        car = SimulatedDevice("robot-car-01", "CAR")
        payload = car.telemetry()
        self.assertIn("wheels", payload)
        self.assertIn("odometer", payload)
        self.assertNotIn("joints", payload)
        self.assertNotIn("gait", payload)
        self.assertTrue(payload["simulated"])
        self.assertEqual(payload["driveMode"], "differential")

    def test_spider_payload_has_16_joints_and_gait(self):
        spider = SimulatedDevice("robot-spider-01", "SPIDER")
        spider.linear = 0.4
        spider.lateral = 0.2
        payload = spider.telemetry()
        self.assertIn("joints", payload)
        self.assertEqual(len(payload["joints"]), 16)
        self.assertIn("gait", payload)
        self.assertEqual(payload["gait"]["legCount"], 8)
        self.assertNotIn("wheels", payload)
        self.assertEqual(payload["driveMode"], "omnidirectional")
        # 关节名必须能被前端 spiderRig 直接消费
        meta = load_spider_rig()
        self.assertTrue(set(payload["joints"]).issubset(set(meta["joints"])))

    def test_dog_and_robot_payload_unchanged(self):
        # ROBOT 期望 11：rig.json 全量 23 关节，模拟器只上报参与摆动的 11 个（5×2 + waist）
        for form_factor, expected in (("DOG", 12), ("ROBOT", 11)):
            device = SimulatedDevice(f"robot-{form_factor.lower()}-01", form_factor)
            payload = device.telemetry()
            self.assertEqual(len(payload["joints"]), expected)
            self.assertNotIn("wheels", payload)
            self.assertNotIn("gait", payload)


if __name__ == "__main__":
    unittest.main()
