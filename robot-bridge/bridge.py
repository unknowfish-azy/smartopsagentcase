"""巡检机器人蓝牙桥（M0）。

功能边界（诚实原则）：
- ``scan``：扫描周边 BLE 设备，输出名称/MAC/RSSI/服务 UUID，用于真机抓包前侦察（详细设计第 7 节待确认项 #1）。
- ``sim``：模拟设备，无硬件时联调「前端 → 后端 → 桥 → 设备 → 遥测」全链路。
- ``run``：真机模式，连接 backend ``/ws/robot/bridge`` 并用 BLE 适配器下发指令；
  真机协议未抓包确认前，适配器会如实报错，不编造字节。

fail-closed：SMARTOPS_ROBOT_BRIDGE_TOKEN 未配置时 run 拒绝启动（exit 2）。
仅依赖标准库 + bleak；不引入其他第三方包。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

TOKEN_ENV = "SMARTOPS_ROBOT_BRIDGE_TOKEN"


async def scan(duration: float) -> int:
    try:
        from bleak import BleakScanner
    except ImportError:
        print("[bridge] 缺少 bleak：请先执行 pip install -r requirements.txt", file=sys.stderr)
        return 1
    print(f"[bridge] 扫描周边 BLE 设备 {duration:.0f}s（用于真机服务 UUID 侦察）…")
    # 新版 bleak 的 BLEDevice 不含 rssi，需同时返回广播数据取信号强度
    found = await BleakScanner.discover(timeout=duration, return_adv=True)
    if not found:
        print("[bridge] 未发现任何 BLE 设备")
        return 0
    entries = sorted(found.values(), key=lambda pair: pair[1].rssi or -999, reverse=True)
    print(f"[bridge] 发现 {len(entries)} 台设备（按 RSSI 降序）：")
    for device, adv in entries:
        uuids = adv.service_uuids or []
        uuid_hint = f"  services={uuids}" if uuids else ""
        print(f"  {device.address}  RSSI={adv.rssi}  name={device.name!r}{uuid_hint}")
    print("[bridge] 下一步：对目标设备抓包确认服务 UUID / 特征值，补齐 protocols/generic_ble_car_v1.py")
    return 0


def run() -> int:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        print(f"[bridge] fail-closed：环境变量 {TOKEN_ENV} 未配置，拒绝启动", file=sys.stderr)
        return 2
    print(f"[bridge] token 自检通过（长度 {len(token)}）。")
    print("[bridge] backend 桥 WS 通道 /ws/robot 于 M1 上线，当前如实退出（不伪装在线）。")
    return 3


def main(argv: list[str] | None = None) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="SmartOps 巡检机器人蓝牙桥")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_parser = sub.add_parser("scan", help="扫描周边 BLE 设备（真机侦察）")
    scan_parser.add_argument("--duration", type=float, default=10.0, help="扫描时长秒数")

    sim_parser = sub.add_parser("sim", help="模拟设备：无硬件联调全链路")
    sim_parser.add_argument("--backend", default=None, help="后端地址，默认 http://127.0.0.1:8080")
    sim_parser.add_argument("--device", default="robot-car-01", help="模拟设备 deviceKey")
    sim_parser.add_argument("--form-factor", default=None,
                             help="形态 CAR/DOG/SPIDER/ROBOT（默认按 deviceKey 尾缀推断）")

    sub.add_parser("run", help="连接 backend 桥通道（真机模式）")

    args = parser.parse_args(raw_args)
    if args.command == "scan":
        return asyncio.run(scan(args.duration))
    if args.command == "sim":
        import sim
        return sim.main(raw_args[1:])
    return run()


if __name__ == "__main__":
    sys.exit(main())
