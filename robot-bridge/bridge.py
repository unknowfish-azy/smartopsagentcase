"""巡检机器人真机/模拟桥。

功能边界（诚实原则）：
- ``scan``：扫描周边 BLE 设备，输出名称/MAC/RSSI/服务 UUID，用于真机抓包前侦察。
- ``sim``：模拟设备，无硬件时联调「前端 → 后端 → 桥 → 设备 → 遥测」全链路。
- ``run``：真机模式，通过 BLE 或串口连接单片机，并接入 backend ``/ws/robot/bridge``；
  仅支持明确实现的协议，编解码失败、参数缺失、鉴权失败均如实报错，不伪装在线。

fail-closed：SMARTOPS_ROBOT_BRIDGE_TOKEN 未配置时 run 拒绝启动（exit 2）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from protocols import get_adapter
from protocols.base import BridgeProtocolError
from transports import BleTransport, BridgeTransportError, SerialTransport

TOKEN_ENV = "SMARTOPS_ROBOT_BRIDGE_TOKEN"
BACKEND_ENV = "SMARTOPS_BACKEND_URL"


class BridgeFatalError(Exception):
    """鉴权/配置等不可通过重连恢复的错误。"""


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
    print("[bridge] 下一步：对目标设备抓包确认服务 UUID / 特征值，或烧写 generic-mcu-v1 配套固件")
    return 0


async def _send_json(socket, message_type: str, payload: dict) -> None:
    await socket.send(json.dumps({"type": message_type, "payload": payload}, ensure_ascii=False))


async def _command_pump(socket, transport, adapter, device_key: str) -> None:
    """后端命令 → 协议帧 → 单片机；不支持的命令只上报拒绝事件，不伪造 ACK。"""
    async for raw in socket:
        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if message.get("type") != "cmd":
            continue
        payload = message.get("payload") or {}
        try:
            frame = adapter.encode_command(payload)
        except BridgeProtocolError as error:
            await _send_json(socket, "event", {
                "deviceKey": device_key,
                "kind": "COMMAND_REJECTED",
                "detail": str(error),
                "op": str(payload.get("op", "")),
            })
            print(f"[bridge] 拒绝命令：{error}")
            continue
        await transport.write(frame)
        print(f"[bridge] 已下发 {str(payload.get('op', '')).upper()} 到 {device_key}")


async def _forward_device_message(socket, adapter, device_key: str, message: dict) -> None:
    channel = message["channel"]
    payload = dict(message["payload"])
    payload["deviceKey"] = device_key
    payload["protocolId"] = adapter.PROTOCOL_ID
    message_type = {"telemetry": "telemetry", "event": "event", "ack": "bridge_ack"}[channel]
    await _send_json(socket, message_type, payload)
    if channel == "ack" and payload.get("status") != "OK":
        print(f"[bridge] 设备 ACK：{payload}")


async def _wait_device_hello(transport, adapter) -> list[dict]:
    """等待真实固件握手；握手期间到达的遥测/事件保留，后端上线后继续转发。"""
    buffered: list[dict] = []
    while True:
        chunk = await transport.read()
        if not chunk:
            raise BridgeTransportError("等待 HELLO_ACK 时单片机断开")
        messages = adapter.feed(chunk)
        buffered.extend(messages)
        for message in messages:
            payload = message["payload"]
            if message["channel"] == "event" and payload.get("kind") == "DEVICE_HELLO":
                if payload.get("protocolVersion") != 1:
                    raise BridgeProtocolError(f"固件协议版本不兼容：{payload.get('protocolVersion')}")
                required = adapter.CAP_MOVE | adapter.CAP_TELEMETRY
                if payload.get("capabilities", 0) & required != required:
                    raise BridgeProtocolError("固件未声明 P0 所需的 MOVE/TELEMETRY 能力")
                return buffered


async def _device_pump(socket, transport, adapter, device_key: str, initial_messages=()) -> None:
    """单片机字节流 → 遥测/事件/ACK → 后端；原始数据不由桥补造。"""
    for message in initial_messages:
        await _forward_device_message(socket, adapter, device_key, message)
    while True:
        chunk = await transport.read()
        if not chunk:
            raise BridgeTransportError("单片机连接已断开")
        for message in adapter.feed(chunk):
            await _forward_device_message(socket, adapter, device_key, message)


async def _run_session(args, adapter, transport, backend: str, token: str) -> None:
    try:
        import websockets
    except ImportError as error:
        raise BridgeFatalError("缺少 websockets：请先执行 pip install -r requirements.txt") from error

    url = backend.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
    url = f"{url}/ws/robot/bridge"
    async with websockets.connect(
        url,
        additional_headers={"X-Robot-Bridge-Token": token},
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
    ) as socket:
        # 设备实际连接并回 HELLO_ACK 后才声明上线，避免后端把“只有桥进程”误认为真机在线。
        adapter.reset()
        await transport.connect()
        await transport.write(adapter.encode_hello())
        try:
            initial_messages = await asyncio.wait_for(_wait_device_hello(transport, adapter), timeout=5)
        except TimeoutError as error:
            raise BridgeTransportError("等待单片机 HELLO_ACK 超时（5s）") from error
        await _send_json(socket, "bridge_hello", {
            "deviceKeys": [args.device],
            "protocols": [adapter.PROTOCOL_ID],
            "formFactor": args.form_factor,
            "transport": args.transport,
            "simulated": False,
        })
        print(f"[bridge] 真机链路已建立：{args.device} / {adapter.PROTOCOL_ID} / {args.transport}")

        tasks = {
            asyncio.create_task(_command_pump(socket, transport, adapter, args.device)),
            asyncio.create_task(_device_pump(socket, transport, adapter, args.device, initial_messages)),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            error = task.exception()
            if error is not None:
                raise error
        if socket.close_code == 1008:
            raise BridgeFatalError("后端拒绝桥连接：请检查 bridge token 与设备接入配置")
        raise BridgeTransportError(f"后端桥通道已关闭（close_code={socket.close_code}）")


async def _run_forever(args, adapter, transport, backend: str, token: str) -> int:
    delay = 1
    while True:
        try:
            await _run_session(args, adapter, transport, backend, token)
        except BridgeFatalError as error:
            print(f"[bridge] 不可重连错误：{error}", file=sys.stderr)
            return 1
        except (BridgeTransportError, BridgeProtocolError, OSError, ValueError) as error:
            print(f"[bridge] 链路断开：{error}")
        except Exception as error:  # 桥进程需保留重连机会，同时如实输出未知异常
            print(f"[bridge] 链路异常：{type(error).__name__}: {error}")
        finally:
            await transport.close()
        print(f"[bridge] {delay}s 后重连；单片机应依靠本地 TTL/失联保护停车")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 5)


async def _run_udp_session(args, backend: str, token: str) -> None:
    """宇树旧 UDP 协议（unitree_legged_sdk，默认 8000 端口）运行会话。

    与 BLE/串口的 adapter+HELLO 流程不同：UDP 是无状态订阅，直接绑端口 → 解码 LowState → 上报后端。
    """
    try:
        import websockets
    except ImportError as error:
        raise BridgeFatalError("缺少 websockets：请先执行 pip install -r requirements.txt") from error

    from transports import UdpTransport
    from unitree_protocol import decode_low_state, go2_joint_dict

    transport = UdpTransport(
        bind_ip=getattr(args, "bind_ip", "0.0.0.0"),
        bind_port=int(getattr(args, "bind_port", 8000)),
        robot_ip=getattr(args, "robot_ip", ""),
        robot_port=int(getattr(args, "robot_port", 8000)),
    )

    url = backend.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
    url = f"{url}/ws/robot/bridge"
    async with websockets.connect(
        url,
        additional_headers={"X-Robot-Bridge-Token": token},
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
    ) as socket:
        await transport.connect()
        await _send_json(socket, "bridge_hello", {
            "deviceKeys": [args.device],
            "protocols": ["unitree-go2-udp-v1"],
            "formFactor": args.form_factor,
            "transport": "udp",
            "simulated": False,
        })
        print(f"[bridge] UDP 链路已建立：{args.device}（unitree_legged_sdk LowState 解码）")

        # 关节缓存：只在 LowState 可用时覆盖，缺失帧保留上次值
        joints_cache: dict[str, float] = {}
        imu_cache: dict | None = None
        battery_cache: float | None = None
        tick_last = 0
        pose_t = 0.0

        async def pump() -> None:
            nonlocal tick_last, joints_cache, imu_cache, battery_cache, pose_t
            last_emit = 0.0
            while True:
                import time
                chunk = await transport.read()
                if not chunk:
                    raise BridgeTransportError("UDP socket 关闭")
                decoded = decode_low_state(chunk)
                if not decoded.get("ok"):
                    continue
                if decoded.get("motorState"):
                    joints = go2_joint_dict(decoded)
                    if joints:
                        joints_cache = joints
                if decoded.get("imu"):
                    imu_cache = decoded["imu"]
                # tick 计数做节奏门限：Go2 LowState 大约 200Hz，桥端限 5Hz 上报
                tick_now = decoded.get("tick", 0)
                if tick_now != tick_last or (time.time() - last_emit) > 0.2:
                    tick_last = tick_now
                    last_emit = time.time()
                    payload = {
                        "deviceKey": args.device,
                        "formFactor": args.form_factor,
                        "driveMode": "quadruped" if args.form_factor == "DOG" else "custom",
                    }
                    if joints_cache:
                        payload["joints"] = joints_cache
                    if imu_cache:
                        payload["imu"] = imu_cache
                    if battery_cache is not None:
                        payload["battery"] = battery_cache
                    await _send_json(socket, "telemetry", payload)

        try:
            await asyncio.gather(pump())
        finally:
            await transport.close()


async def _run_udp_forever(args, backend: str, token: str) -> int:
    delay = 1
    while True:
        try:
            await _run_udp_session(args, backend, token)
        except BridgeFatalError as error:
            print(f"[bridge] UDP 不可重连错误：{error}", file=sys.stderr)
            return 1
        except (BridgeTransportError, OSError) as error:
            print(f"[bridge] UDP 链路断开：{error}")
        except Exception as error:
            print(f"[bridge] UDP 链路异常：{type(error).__name__}: {error}")
        print(f"[bridge] {delay}s 后重连 UDP 订阅")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 5)


def run(args) -> int:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        print(f"[bridge] fail-closed：环境变量 {TOKEN_ENV} 未配置，拒绝启动", file=sys.stderr)
        return 2
    backend = (args.backend or os.environ.get(BACKEND_ENV, "http://127.0.0.1:8080")).strip()
    if args.transport == "udp":
        return _run_udp_forever(args, backend, token)
    if args.transport == "ble" and not all((args.mac, args.service_uuid, args.write_char_uuid, args.notify_char_uuid)):
        print("[bridge] BLE 模式必须提供 --mac/--service-uuid/--write-char-uuid/--notify-char-uuid", file=sys.stderr)
        return 2
    if args.transport == "serial" and not args.port:
        print("[bridge] 串口模式必须提供 --port", file=sys.stderr)
        return 2

    try:
        adapter = get_adapter(
            args.protocol,
            service_uuid=args.service_uuid or "",
            write_char_uuid=args.write_char_uuid or "",
            notify_char_uuid=args.notify_char_uuid or "",
        )
    except BridgeProtocolError as error:
        print(f"[bridge] {error}", file=sys.stderr)
        return 2
    transport = (
        BleTransport(args.mac, adapter.SERVICE_UUID, adapter.WRITE_CHAR_UUID, adapter.NOTIFY_CHAR_UUID)
        if args.transport == "ble"
        else SerialTransport(args.port, args.baud)
    )
    try:
        return asyncio.run(_run_forever(args, adapter, transport, backend, token))
    except KeyboardInterrupt:
        print("\n[bridge] 已退出；请确认单片机已按本地安全策略停车")
        return 0


def main(argv: list[str] | None = None) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="SmartOps 巡检机器人真机/模拟桥")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_parser = sub.add_parser("scan", help="扫描周边 BLE 设备（真机侦察）")
    scan_parser.add_argument("--duration", type=float, default=10.0, help="扫描时长秒数")

    sim_parser = sub.add_parser("sim", help="模拟设备：无硬件联调全链路")
    sim_parser.add_argument("--backend", default=None, help="后端地址，默认 http://127.0.0.1:8080")
    sim_parser.add_argument("--device", default="robot-car-01", help="模拟设备 deviceKey")
    sim_parser.add_argument("--form-factor", default=None,
                             help="形态 CAR/DOG/SPIDER/ROBOT（默认按 deviceKey 尾缀推断）")

    run_parser = sub.add_parser("run", help="真机模式：BLE/串口/UDP 设备接入后端桥通道")
    run_parser.add_argument("--backend", default=None, help=f"后端地址，默认读取 {BACKEND_ENV}")
    run_parser.add_argument("--device", required=True, help="已登记并启用的设备 deviceKey")
    run_parser.add_argument("--form-factor", choices=["CAR", "DOG", "SPIDER", "ROBOT"], default="CAR")
    run_parser.add_argument("--protocol", choices=["generic-mcu-v1"], default="generic-mcu-v1")
    run_parser.add_argument("--transport", choices=["ble", "serial", "udp"], required=True)
    run_parser.add_argument("--mac", help="BLE 设备 MAC/系统地址")
    run_parser.add_argument("--service-uuid", default="", help="BLE 自定义服务 UUID")
    run_parser.add_argument("--write-char-uuid", default="", help="BLE 指令写特征值 UUID")
    run_parser.add_argument("--notify-char-uuid", default="", help="BLE 遥测通知特征值 UUID")
    run_parser.add_argument("--port", help="串口名，如 COM5 或 /dev/ttyUSB0")
    run_parser.add_argument("--baud", type=int, default=115200, help="串口波特率，默认 115200")
    # UDP（宇树 unitree_legged_sdk 旧协议）
    run_parser.add_argument("--bind-ip", default="0.0.0.0", help="UDP 本地绑定 IP（默认 0.0.0.0）")
    run_parser.add_argument("--bind-port", type=int, default=8000, help="UDP 本地绑定端口（Go2 默认 8000）")
    run_parser.add_argument("--robot-ip", default="192.168.123.161", help="机器人目标 IP（Go2 默认 192.168.123.161）")
    run_parser.add_argument("--robot-port", type=int, default=8000, help="机器人目标端口（默认 8000）")

    args = parser.parse_args(raw_args)
    if args.command == "scan":
        return asyncio.run(scan(args.duration))
    if args.command == "sim":
        import sim
        return sim.main(raw_args[1:])
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
