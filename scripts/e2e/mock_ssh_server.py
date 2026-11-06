#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E 专用本地 mock SSH 服务器 —— 2026-11-06 晚（SEC-04/05 审批链路验收）。

为什么需要它：团队运行（TeamAgentRun）的 create/execute 都要求一个
`OperationRuntimeRegistry` 里归申请人所有的 runtime，而 runtime 只能由
`SshConnectionAdapter` 通过真实 SSH 连接注册。本脚本在本机 2222 端口起一个
最小 SSH 服务器（paramiko），供后端拨号注册 runtime；exec 命令不真正执行，
回显命令并返回退出码 0（验收断言的是安全链路，不是远端执行结果）。

凭据（与 E2E 脚本约定一致）：
  host 127.0.0.1  port 2222  user e2eops  password E2eSsh#2026

用法（Python 3.14，已装 paramiko 5.0）：
  C:/Users/33908/AppData/Local/Programs/Python/Python314/python.exe scripts/e2e/mock_ssh_server.py
"""

from __future__ import annotations

import socket
import sys
import threading

import paramiko

HOST = "127.0.0.1"
PORT = 2222
USERNAME = "e2eops"
PASSWORD = "E2eSsh#2026"

# 启动时生成一次性主机密钥（仅本进程生命周期内有效，验收完即弃）
HOST_KEY = paramiko.RSAKey.generate(2048)

# 保持所有存活通道的引用，避免被 GC 断链
_CHANNELS: set = set()
_LOCK = threading.Lock()


class MockSSHServer(paramiko.ServerInterface):
    def get_allowed_auths(self, username):
        return "password"

    def check_auth_password(self, username, password):
        if username == USERNAME and password == PASSWORD:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        if kind in ("session", "direct-tcpip"):
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        with _LOCK:
            _CHANNELS.add(channel)
        threading.Thread(target=self._exec, args=(channel, command), daemon=True).start()
        return True

    def check_channel_shell_request(self, channel):
        # 交互 shell：onOutput() 会开 shell 通道；回个提示即可，工具执行走 exec
        try:
            channel.sendall(b"[e2e-mock] shell ready\r\n")
        except Exception:
            pass
        return True

    @staticmethod
    def _exec(channel, command):
        try:
            text = command.decode("utf-8", "replace") if isinstance(command, bytes) else str(command)
            channel.sendall(f"[e2e-mock] executed: {text}\n".encode("utf-8"))
            channel.sendall(b"[e2e-mock] exit 0\n")
            channel.send_exit_status(0)
        except Exception as err:  # 连接被客户端关闭等
            print(f"[mock-ssh] exec error: {err}", file=sys.stderr, flush=True)
        finally:
            try:
                channel.shutdown_write()
                channel.close()
            except Exception:
                pass
            with _LOCK:
                _CHANNELS.discard(channel)


def handle(client: socket.socket, addr):
    transport = paramiko.Transport(client)
    transport.add_server_key(HOST_KEY)
    server = MockSSHServer()
    try:
        transport.start_server(server=server)
        # 持续接收该连接上的通道（每个 exec 命令一条）
        while transport.is_active():
            channel = transport.accept(timeout=30)
            if channel is None:
                continue
            with _LOCK:
                _CHANNELS.add(channel)
    except Exception as err:
        print(f"[mock-ssh] conn {addr} error: {err}", file=sys.stderr, flush=True)
    finally:
        try:
            transport.close()
        except Exception:
            pass


def main():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((HOST, PORT))
    listener.listen(16)
    print(f"[mock-ssh] listening on {HOST}:{PORT} (user={USERNAME})", flush=True)
    while True:
        client, addr = listener.accept()
        threading.Thread(target=handle, args=(client, addr), daemon=True).start()


if __name__ == "__main__":
    main()
