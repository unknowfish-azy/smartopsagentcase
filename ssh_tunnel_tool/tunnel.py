"""Paramiko SSH 端口转发生命周期管理。"""

from __future__ import annotations

import socket
import socketserver
import threading
from dataclasses import dataclass
from enum import Enum

import paramiko


class TunnelStatus(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    ERROR = "ERROR"


def status_presentation(status: TunnelStatus) -> tuple[str, str]:
    """返回同时适合文本和颜色呈现的状态，颜色不承担唯一语义。"""
    return {
        TunnelStatus.RUNNING: ("运行中", "#2e9b62"),
        TunnelStatus.STOPPED: ("已停止", "#7a7a7a"),
        TunnelStatus.ERROR: ("连接失败", "#c33c3c"),
        TunnelStatus.STARTING: ("连接中", "#b88427"),
    }.get(status, ("未知状态", "#7a7a7a"))


@dataclass
class TunnelConfig:
    name: str
    tunnel_type: str = "LOCAL"
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_user: str = ""
    listen_host: str = "127.0.0.1"
    listen_port: int = 1080
    target_host: str = ""
    target_port: int = 0
    password: str | None = None
    auth_method: str = "password"
    private_key_path: str = ""
    connect_timeout: int = 10
    keepalive_seconds: int = 30
    compression: bool = False
    auto_reconnect: bool = False


def validate_tunnel_config(config: TunnelConfig) -> None:
    if not config.name.strip():
        raise ValueError("隧道名称不能为空")
    if not config.ssh_host.strip() or not config.ssh_user.strip():
        raise ValueError("SSH 主机和用户名不能为空")
    if config.auth_method not in {"password", "private_key"}:
        raise ValueError("认证方式必须是密码或私钥文件")
    if config.auth_method == "private_key" and not config.private_key_path.strip():
        raise ValueError("私钥认证必须选择私钥文件")
    if config.tunnel_type not in {"LOCAL", "REMOTE", "DYNAMIC"}:
        raise ValueError("隧道类型必须是 LOCAL、REMOTE 或 DYNAMIC")
    if not 1 <= config.ssh_port <= 65535:
        raise ValueError("SSH 端口必须在 1-65535 范围内")
    if not 1 <= config.connect_timeout <= 120:
        raise ValueError("连接超时必须在 1-120 秒范围内")
    if not 0 <= config.keepalive_seconds <= 3600:
        raise ValueError("Keepalive 必须在 0-3600 秒范围内")
    if config.tunnel_type != "DYNAMIC":
        if not config.target_host.strip():
            raise ValueError("Local/Remote 模式必须填写目标服务器")
        if not 1 <= config.target_port <= 65535:
            raise ValueError("目标端口必须在 1-65535 范围内")
    if not 1 <= config.listen_port <= 65535:
        raise ValueError("本地监听端口必须在 1-65535 范围内")


class _ForwardHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        channel = self.server.transport.open_channel("direct-tcpip", self.server.target, self.request.getpeername())
        try:
            _relay(self.request, channel)
        finally:
            channel.close()


class _ForwardServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, address, transport, target):
        self.transport = transport
        self.target = target
        super().__init__(address, _ForwardHandler)


class _SocksHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        request = self.request
        if request.recv(1) != b"\x05":
            return
        methods = request.recv(1)[0]
        request.recv(methods)
        request.sendall(b"\x05\x00")
        if request.recv(4) != b"\x05\x01\x00":
            return
        address_type = request.recv(1)[0]
        if address_type == 1:
            host = socket.inet_ntoa(request.recv(4))
        elif address_type == 3:
            host = request.recv(1)[0]
            host = request.recv(host).decode()
        else:
            return
        port = int.from_bytes(request.recv(2), "big")
        channel = self.server.transport.open_channel("direct-tcpip", (host, port), request.getpeername())
        request.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
        try:
            _relay(request, channel)
        finally:
            channel.close()


class _SocksServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, address, transport):
        self.transport = transport
        super().__init__(address, _SocksHandler)


def _relay(left, right) -> None:
    left.settimeout(0.5)
    right.settimeout(0.5)
    while True:
        readable, _, _ = __import__("select").select([left, right], [], [], 0.5)
        if not readable:
            continue
        for source, target in ((left, right), (right, left)):
            if source not in readable:
                continue
            data = source.recv(65536)
            if not data:
                return
            target.sendall(data)


class TunnelManager:
    def __init__(self) -> None:
        self._active: dict[str, tuple[paramiko.SSHClient, socketserver.BaseServer | None, threading.Thread | None]] = {}
        self._statuses: dict[str, TunnelStatus] = {}
        self._lock = threading.RLock()
        self._configs: dict[str, TunnelConfig] = {}
        self._credentials: dict[str, str | None] = {}
        self._cancelled: set[str] = set()
        self._monitor_stop = threading.Event()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, name="ssh-tunnel-monitor", daemon=True)
        self._monitor_thread.start()

    def status(self, name: str) -> TunnelStatus:
        return self._statuses.get(name, TunnelStatus.STOPPED)

    def start(self, config: TunnelConfig, password: str | None = None) -> None:
        """异步启动隧道，SSH 连接和转发监听均不阻塞调用线程。"""
        validate_tunnel_config(config)
        with self._lock:
            if self.status(config.name) in {TunnelStatus.STARTING, TunnelStatus.RUNNING}:
                return
            self._statuses[config.name] = TunnelStatus.STARTING
            self._configs[config.name] = config
            self._credentials[config.name] = password
            self._cancelled.discard(config.name)
        threading.Thread(
            target=self._start_worker,
            args=(config, password),
            name=f"ssh-tunnel-{config.name}",
            daemon=True,
        ).start()

    def _start_worker(self, config: TunnelConfig, password: str | None) -> None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        server = None
        try:
            connect_kwargs = {
                "hostname": config.ssh_host,
                "port": config.ssh_port,
                "username": config.ssh_user,
                "timeout": config.connect_timeout,
                "compress": config.compression,
            }
            if config.auth_method == "private_key":
                connect_kwargs["key_filename"] = config.private_key_path
            else:
                connect_kwargs["password"] = password
            client.connect(**connect_kwargs)
            transport = client.get_transport()
            if transport and config.keepalive_seconds:
                transport.set_keepalive(config.keepalive_seconds)
            if config.tunnel_type == "LOCAL":
                server = _ForwardServer((config.listen_host, config.listen_port), transport, (config.target_host, config.target_port))
            elif config.tunnel_type == "DYNAMIC":
                server = _SocksServer((config.listen_host, config.listen_port), transport)
            else:
                transport.request_port_forward(config.listen_host, config.listen_port)
            server_thread = None
            if server:
                server_thread = threading.Thread(target=server.serve_forever, name=f"forward-{config.name}", daemon=True)
                server_thread.start()
            with self._lock:
                if config.name in self._cancelled:
                    if server:
                        server.shutdown()
                        server.server_close()
                    client.close()
                    self._cancelled.discard(config.name)
                    self._statuses[config.name] = TunnelStatus.STOPPED
                    return
                self._active[config.name] = (client, server, server_thread)
                self._statuses[config.name] = TunnelStatus.RUNNING
        except Exception:
            if server:
                server.server_close()
            client.close()
            with self._lock:
                self._statuses[config.name] = TunnelStatus.ERROR
            raise

    def _monitor_loop(self) -> None:
        """后台检测 SSH transport；断线后更新状态并按配置自动重连。"""
        while not self._monitor_stop.wait(1.0):
            with self._lock:
                active_items = list(self._active.items())
            for name, (client, server, _server_thread) in active_items:
                transport = client.get_transport()
                healthy = bool(transport and transport.is_active())
                if server and getattr(server, "_BaseServer__shutdown_request", False):
                    healthy = False
                if healthy:
                    continue
                with self._lock:
                    self._active.pop(name, None)
                    config = self._configs.get(name)
                    self._statuses[name] = TunnelStatus.ERROR
                if server:
                    server.server_close()
                client.close()
                if config and config.auto_reconnect:
                    self.start(config, password=self._credentials.get(name))

    def stop(self, name: str) -> None:
        with self._lock:
            active = self._active.pop(name, None)
            if self._statuses.get(name) == TunnelStatus.STARTING:
                self._cancelled.add(name)
                self._statuses[name] = TunnelStatus.STOPPED
        if not active:
            self._statuses[name] = TunnelStatus.STOPPED
            return
        client, server, server_thread = active
        if server:
            server.shutdown()
            server.server_close()
        if server_thread and server_thread.is_alive() and server_thread is not threading.current_thread():
            server_thread.join(timeout=2.0)
        client.close()
        self._statuses[name] = TunnelStatus.STOPPED

    def close(self) -> None:
        self._monitor_stop.set()
        self.stop_all()

    def stop_all(self) -> None:
        for name in list(self._active):
            self.stop(name)

    def start_all(self, configs, password_provider) -> dict:
        """逐条启动全部隧道，返回成功列表和失败详情。"""
        started, failed = [], {}
        for config in configs:
            try:
                self.start(config, password=password_provider(config))
                started.append(config.name)
            except Exception as error:
                failed[config.name] = str(error)
        return {"started": started, "failed": failed}
