"""模拟巡检机器人（无硬件全链路联调用）。

支持多形态模拟：
  - CAR (diff)      差速巡检车：仅前进/后退 + 转向，横移无效
  - DOG (quad)      四足机器狗：前进/后退 + 转向 + 弱横移（走路时侧向漂移）
  - SPIDER (omni)   全向蜘蛛/麦克纳姆：x/y/theta 三轴独立
  - ROBOT (custom)  自定义/人形：同蜘蛛，按台账 capabilities 决定

叠声明：本模块是**模拟器**，不连接任何物理设备；遥测数值由运动积分算出，
仅用于联调，不得作为设备真实性能或巡检结论的依据。

形态独立遥测（不影响 DOG/ROBOT 既有字段）：
  - CAR：wheels（左右轮线速度/角速度、轮半径、轮距、LiDAR 转速）+ odometer；
  - SPIDER：joints（8 足 16 关节，Leg{i}_hip / Leg{i}_knee，与 spider-bot.rig.json 同名）
    + gait（步态相位、8 足触地状态、机身高度）。

用法：
    $env:SMARTOPS_ROBOT_BRIDGE_TOKEN = "dev-token"
    python robot-bridge\\bridge.py sim --device robot-car-01 --form-factor CAR
    python robot-bridge\\bridge.py sim --device robot-dog-01 --form-factor DOG
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import os
import struct
import sys
import time
import zlib

# 本地 gait_solver：同目录下相对导入，桥进程（__main__）需要 sys.path 调整
try:
    from gait_solver import quadruped_joints, humanoid_joints, spider_joints, spider_gait  # type: ignore
except ImportError:
    from .gait_solver import quadruped_joints, humanoid_joints, spider_joints, spider_gait  # type: ignore

TELEMETRY_INTERVAL = 0.2      # 5Hz 遥测上报
HEARTBEAT_TIMEOUT = 0.5       # 超过该时长未收到 MOVE 即视为松手
FRAME_WIDTH = 160
FRAME_HEIGHT = 90
SUPPORTED_FORM_FACTORS = ("CAR", "DOG", "SPIDER", "ROBOT")

# 巡检车（CAR）差速底盘参数，与 frontend/models/patrolCarModel.js 的轮半径一致
CAR_WHEEL_RADIUS = 0.075
CAR_TRACK_WIDTH = 0.32
CAR_LIDAR_RPM = 600


def car_wheel_speeds(linear: float, angular: float) -> dict:
    """差速车左右轮遥测：直行等速、转向时内外轮差速。

    Args:
        linear: 车体前进线速度（m/s）
        angular: 转向输入（-1..1），与 tick() 中 heading += angular * 60°/s 同口径
    """
    omega = math.radians(angular * 60.0)   # rad/s
    half = CAR_TRACK_WIDTH / 2
    left = linear - omega * half
    right = linear + omega * half
    return {
        "radius": CAR_WHEEL_RADIUS,
        "trackWidth": CAR_TRACK_WIDTH,
        "leftSpeed": round(left, 3),
        "rightSpeed": round(right, 3),
        "leftAngular": round(left / CAR_WHEEL_RADIUS, 2),
        "rightAngular": round(right / CAR_WHEEL_RADIUS, 2),
        "lidarRpm": CAR_LIDAR_RPM,
    }


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def synth_frame_base64() -> str:
    """合成一张灰度渐变 PNG 作为「摄像头关键帧」。

    叠声明：这不是真实画面，仅用于在无真机时验证
    「CAPTURE → 帧回传 → 后端视觉巡检」链路是否通。
    """
    raw = bytearray()
    for y in range(FRAME_HEIGHT):
        raw.append(0)  # filter type 0
        for x in range(FRAME_WIDTH):
            value = int(255 * (0.6 * x / FRAME_WIDTH + 0.4 * y / FRAME_HEIGHT))
            raw.extend((value, value, value))
    header = struct.pack(">IIBBBBB", FRAME_WIDTH, FRAME_HEIGHT, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + _png_chunk(b"IHDR", header)
           + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + _png_chunk(b"IEND", b""))
    return base64.b64encode(png).decode("ascii")


class SimulatedDevice:
    """按 form_factor 选择不同运动学模型的模拟设备。

    四套模型对应 RobotTeleopProfiles.java 里 CAR/DOG/SPIDER/ROBOT 的
    driveMode 定义：differential / quadruped / omnidirectional / custom。
    """

    def __init__(self, device_key: str, form_factor: str = "CAR") -> None:
        self.device_key = device_key
        self.form_factor = (form_factor or "CAR").upper()
        if self.form_factor not in SUPPORTED_FORM_FACTORS:
            raise ValueError(f"不支持的形态：{form_factor}（支持 {SUPPORTED_FORM_FACTORS}）")
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.battery = 0.92
        self.obstacle = 2.4
        self.linear = 0.0
        self.lateral = 0.0
        self.angular = 0.0
        self.last_command_at = 0.0
        self.last_tick = time.monotonic()
        self.frames_pending = 0
        self.sim_start_time = time.monotonic()
        self.odometer = 0.0

    @property
    def drive_mode(self) -> str:
        return {
            "CAR": "differential",
            "DOG": "quadruped",
            "SPIDER": "omnidirectional",
            "ROBOT": "custom",
        }.get(self.form_factor, "custom")

    def apply(self, op: str, params: dict) -> None:
        if op == "MOVE":
            speed = float(params.get("speed", 0.5))
            raw_x = float(params.get("x", 0))
            raw_y = float(params.get("y", 0))
            raw_theta = float(params.get("theta", 0)) * speed

            # 形态化处理：后端下发一致的 x/y/theta 向量，模拟器按物理约束裁剪
            if self.form_factor == "CAR":
                # 差速车：y 轴无效（除非速度接近 0 的微转向补偿）
                self.linear = raw_x * speed
                self.lateral = 0.0
                self.angular = raw_theta
            elif self.form_factor == "DOG":
                # 四足：前进后退 + 转向 + 弱横移（走路时自然漂移）
                self.linear = raw_x * speed
                self.lateral = raw_y * speed * 0.25  # 侧向漂移系数 25%
                self.angular = raw_theta
            elif self.form_factor == "SPIDER":
                # 全向：三轴完全独立
                self.linear = raw_x * speed
                self.lateral = raw_y * speed
                self.angular = raw_theta
            else:  # ROBOT / custom
                self.linear = raw_x * speed
                self.lateral = raw_y * speed
                self.angular = raw_theta

            self.last_command_at = time.monotonic()
        elif op == "STOP":
            self.linear = 0.0
            self.lateral = 0.0
            self.angular = 0.0
        elif op == "CAPTURE":
            self.frames_pending += 1

    def tick(self) -> None:
        now = time.monotonic()
        dt = max(0.0, min(0.5, now - self.last_tick))
        self.last_tick = now
        if self.linear or self.lateral or self.angular:
            if now - self.last_command_at > HEARTBEAT_TIMEOUT:
                self.linear = 0.0
                self.lateral = 0.0
                self.angular = 0.0
        self.heading = (self.heading + self.angular * 60.0 * dt) % 360
        radians = math.radians(self.heading)
        prev_x, prev_y = self.x, self.y
        self.x += (math.cos(radians) * self.linear - math.sin(radians) * self.lateral) * dt
        self.y += (math.sin(radians) * self.linear + math.cos(radians) * self.lateral) * dt
        # 里程按实际位移积分（含横移），供 CAR 遥测 odometer 使用
        self.odometer += math.hypot(self.x - prev_x, self.y - prev_y)
        # 电量：DOG/ROBOT 能耗略高（四足走路/人形关节更多）
        drain_factor = {"CAR": 1.0, "DOG": 1.5, "SPIDER": 1.2, "ROBOT": 1.3}[self.form_factor]
        self.battery = max(0.05, min(1.0, self.battery - abs(self.linear) * 0.0004 * drain_factor * dt))
        self.obstacle = max(0.2, 2.4 - abs(self.x) * 0.05)

    def _sim_joints(self) -> dict | None:
        """步态求解 → 关节角；CAR 无关节返回 None。"""
        t = time.monotonic() - self.sim_start_time
        if self.form_factor == "DOG":
            return quadruped_joints(self.linear, self.angular, t)
        if self.form_factor == "ROBOT":
            return humanoid_joints(self.linear, self.angular, t)
        if self.form_factor == "SPIDER":
            return spider_joints(self.linear, self.lateral, self.angular, t)
        return None

    def _sim_gait(self) -> dict:
        """蜘蛛形态专属步态遥测（相位 / 触地 / 机身高度）。"""
        t = time.monotonic() - self.sim_start_time
        return spider_gait(self.linear, self.lateral, self.angular, t)

    def telemetry(self) -> dict:
        payload = {
            "deviceKey": self.device_key,
            "formFactor": self.form_factor,
            "driveMode": self.drive_mode,
            "battery": round(self.battery, 3),
            "pose": {"x": round(self.x, 2), "y": round(self.y, 2), "theta": round(self.heading, 1)},
            "obstacleDistance": round(self.obstacle, 2),
            "simulated": True,
        }
        joints = self._sim_joints()
        if joints:
            payload["joints"] = joints
        # 形态独立遥测：CAR 上报左右轮速与里程，SPIDER 上报步态相态（DOG/ROBOT 不变）
        if self.form_factor == "CAR":
            payload["wheels"] = car_wheel_speeds(self.linear, self.angular)
            payload["odometer"] = round(self.odometer, 2)
        elif self.form_factor == "SPIDER":
            payload["gait"] = self._sim_gait()
        return payload


async def run(backend: str, token: str, device_key: str, form_factor: str = "CAR") -> int:
    try:
        import websockets
    except ImportError:
        print("[sim] 缺少 websockets：请先执行 pip install -r requirements.txt")
        return 1

    url = backend.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
    url = f"{url}/ws/robot/bridge"
    device = SimulatedDevice(device_key, form_factor)

    print(f"[sim] 连接桥通道 {url}（设备 {device_key} 形态 {form_factor}/{device.drive_mode}）")
    try:
        async with websockets.connect(url, additional_headers={"X-Robot-Bridge-Token": token}) as socket:
            await socket.send(json.dumps({
                "type": "bridge_hello",
                "payload": {
                    "deviceKeys": [device_key],
                    "protocols": ["sim-v1"],
                    "simulated": True,
                    "formFactor": form_factor,
                },
            }))
            print("[sim] 已声明设备，开始以 5Hz 上报遥测；Ctrl+C 退出")

            async def pump_commands() -> None:
                async for raw in socket:
                    try:
                        message = json.loads(raw)
                    except ValueError:
                        continue
                    if message.get("type") != "cmd":
                        continue
                    payload = message.get("payload") or {}
                    op = str(payload.get("op", "")).upper()
                    params = payload.get("params") or {}
                    device.apply(op, params)
                    print(f"[sim] 收到命令 {op} {params}")

            async def pump_telemetry() -> None:
                while True:
                    device.tick()
                    await socket.send(json.dumps({"type": "telemetry", "payload": device.telemetry()}))
                    if device.frames_pending > 0:
                        device.frames_pending -= 1
                        await socket.send(json.dumps({"type": "frame", "payload": {
                            "deviceKey": device.device_key,
                            "imageBase64": synth_frame_base64(),
                            "mime": "image/png",
                            "quality": "sim",
                            "simulated": True,
                        }}))
                        print("[sim] 已回传合成关键帧（非真实画面）")
                    await asyncio.sleep(TELEMETRY_INTERVAL)

            await asyncio.gather(pump_commands(), pump_telemetry())
    except KeyboardInterrupt:
        print("[sim] 已退出")
        return 0
    except Exception as error:  # noqa: BLE001 - 桥侧需要把任何连接错误如实报出
        print(f"[sim] 连接失败：{error}")
        return 1
    return 0


def main(argv: list[str]) -> int:
    backend = os.environ.get("SMARTOPS_BACKEND_URL", "http://127.0.0.1:8080")
    token = os.environ.get("SMARTOPS_ROBOT_BRIDGE_TOKEN", "").strip()

    parser = argparse.ArgumentParser(description="SmartOps 巡检机器人模拟器")
    parser.add_argument("--device", default="robot-car-01", help="模拟设备 deviceKey")
    parser.add_argument("--backend", default=None, help="后端地址")
    parser.add_argument("--form-factor", default=None,
                        help=f"形态：{'/'.join(SUPPORTED_FORM_FACTORS)}（默认按 deviceKey 尾缀或 CAR）")
    args = parser.parse_args(argv)

    device_key = args.device
    if args.backend:
        backend = args.backend

    # 推断形态：显式参数 > deviceKey 尾缀 > CAR 兜底
    form_factor = args.form_factor
    if form_factor is None:
        for suffix in ("car", "dog", "spider", "robot"):
            if device_key.lower().endswith(f"-{suffix}-01") or device_key.lower().endswith(f"-{suffix}"):
                form_factor = suffix.upper()
                break
    if form_factor is None:
        form_factor = "CAR"

    if not token:
        print("[sim] fail-closed：环境变量 SMARTOPS_ROBOT_BRIDGE_TOKEN 未配置，拒绝启动")
        return 2

    return asyncio.run(run(backend, token, device_key, form_factor))
