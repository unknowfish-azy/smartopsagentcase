"""
SmartOps MCP 传输层。

实现 MCP 规范定义的 **stdio** 传输（spec：客户端应尽可能支持 stdio）：

    - `StdioServerTransport`：服务端侧，从 stdin 读一行 JSON-RPC、向 stdout 写一行；
      日志**只写 stderr**，stdout 不得出现任何非 MCP 消息。
    - `StdioClientTransport`：客户端侧，把 MCP server 作为子进程拉起，
      维护请求 id → Future 的关联，并把子进程 stderr 转发到日志。

设计说明：
    * 协议与传输解耦——编解码在 `protocol.py`，这里只管管道与分帧。
    * 不依赖任何 MCP SDK；Windows / POSIX 均可用。
    * Streamable HTTP 传输按规范属于另一条通道，本轮不实现（见模块末尾说明），
      避免留下"看起来支持、实际未验证"的代码。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Callable

from .protocol import (
    MCPError,
    decode_message,
    encode_message,
    is_response,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 30.0
_CLOSE_TIMEOUT_SECONDS = 5.0


# ------------------------------------------------------------------
# 服务端侧
# ------------------------------------------------------------------

class StdioServerTransport:
    """服务端 stdio 传输。

    同步读写（`sys.stdin` / `sys.stdout`），由调用方决定如何放进事件循环。
    这样在 Windows 与 POSIX 上行为一致，也避免对标准句柄做异步包装的平台差异。

    纪律（spec transports / stdio）：
        * stdout 只写 MCP 消息；
        * 日志写 stderr；
        * 消息以换行分隔且不含内嵌换行（由 `encode_message` 保证）。
    """

    def __init__(
        self,
        *,
        stdin=None,
        stdout=None,
        stderr=None,
    ) -> None:
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr

    def read_line(self) -> str | None:
        """读取一行；EOF 返回 None。"""

        line = self._stdin.readline()

        if not line:
            return None

        return line.rstrip("\r\n")

    def write_message(
        self,
        message: dict[str, Any],
    ) -> None:
        """写一条 MCP 消息（单行 JSON + 换行）。"""

        self._stdout.write(
            encode_message(message) + "\n"
        )
        self._stdout.flush()

    def log(
        self,
        message: str,
    ) -> None:
        """日志写 stderr，绝不污染 stdout。"""

        self._stderr.write(
            f"[smartops-mcp] {message}\n"
        )
        self._stderr.flush()


# ------------------------------------------------------------------
# 客户端侧
# ------------------------------------------------------------------

class StdioClientTransport:
    """客户端 stdio 传输：把 MCP server 作为子进程管理。

    用法：

        transport = StdioClientTransport([sys.executable, "-m", "agent.mcp"])
        await transport.start()
        response = await transport.request("initialize", {...})
        await transport.notify("notifications/initialized")
        await transport.close()
    """

    def __init__(
        self,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        stderr_handler: Callable[[str], None] | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not command:
            raise ValueError("command 不能为空")

        self.command = list(command)
        self.env = dict(env or os.environ)
        self.timeout = timeout
        self._stderr_handler = stderr_handler

        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._pending: dict[
            int | str,
            asyncio.Future,
        ] = {}
        self._incoming: asyncio.Queue = asyncio.Queue()
        self._closed = False

    # -- 生命周期 -----------------------------------------------------

    async def start(self) -> None:
        """启动子进程并启动读取循环。"""

        if self._process is not None:
            raise MCPError("传输已启动")

        self._process = (
            await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
        )

        self._reader_task = (
            asyncio.create_task(
                self._read_loop(),
                name="mcp-stdio-reader",
            )
        )
        self._stderr_task = (
            asyncio.create_task(
                self._stderr_loop(),
                name="mcp-stdio-stderr",
            )
        )

    async def close(self) -> None:
        """关闭传输：先关子进程 stdin，再按 SIGTERM → SIGKILL 收敛。"""

        if self._closed:
            return

        self._closed = True

        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

        process = self._process
        self._process = None

        if process is None:
            return

        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:  # noqa: BLE001 — 关闭失败不应掩盖主流程
            logger.debug(
                "mcp transport: 关闭子进程 stdin 失败",
                exc_info=True,
            )

        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=_CLOSE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "mcp transport: 子进程未在 %ss 内退出，发送 SIGTERM",
                _CLOSE_TIMEOUT_SECONDS,
            )
            process.terminate()
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=_CLOSE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "mcp transport: SIGTERM 后仍未退出，发送 SIGKILL"
                )
                process.kill()
                await process.wait()

        for task in (
            self._reader_task,
            self._stderr_task,
        ):
            if task is not None and not task.done():
                task.cancel()

    # -- 消息交换 -----------------------------------------------------

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        message_id: int | str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """发送请求并等待同 id 响应。"""

        if self._process is None or self._closed:
            raise MCPError("传输未启动或已关闭")

        request_id = (
            message_id
            if message_id is not None
            else id(asyncio.current_task()) & 0x7FFFFFFF
        )

        future: asyncio.Future = (
            asyncio.get_event_loop().create_future()
        )
        self._pending[request_id] = future

        from .protocol import make_request

        await self._send_raw(
            make_request(
                message_id=request_id,
                method=method,
                params=params,
            )
        )

        try:
            return await asyncio.wait_for(
                future,
                timeout=(
                    timeout
                    if timeout is not None
                    else self.timeout
                ),
            )
        except asyncio.TimeoutError as exc:
            raise MCPError(
                f"MCP 请求超时：{method}",
                data={"timeout_seconds": self.timeout},
            ) from exc
        finally:
            self._pending.pop(request_id, None)

    async def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """发送通知（不期待响应）。"""

        if self._process is None or self._closed:
            raise MCPError("传输未启动或已关闭")

        from .protocol import make_notification

        await self._send_raw(
            make_notification(
                method=method,
                params=params,
            )
        )

    async def receive_incoming(self) -> dict[str, Any]:
        """取出服务端主动发来的通知/请求（供需要双向通信的场景）。"""

        return await self._incoming.get()

    # -- 内部 --------------------------------------------------------

    async def _send_raw(
        self,
        message: dict[str, Any],
    ) -> None:
        process = self._process

        if process is None or process.stdin is None:
            raise MCPError("子进程不可写")

        process.stdin.write(
            (encode_message(message) + "\n").encode("utf-8")
        )
        await process.stdin.drain()

    async def _read_loop(self) -> None:
        process = self._process

        if process is None or process.stdout is None:
            return

        assert process.stdout is not None

        while True:
            try:
                raw = await process.stdout.readline()
            except Exception:  # noqa: BLE001 — 读循环退出交由 closed 语义
                logger.debug(
                    "mcp transport: 读取子进程 stdout 出错",
                    exc_info=True,
                )
                break

            if not raw:
                break

            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")

            if not line.strip():
                continue

            try:
                message = decode_message(line)
            except MCPError as exc:
                logger.warning(
                    "mcp transport: 无法解析子进程消息：%s",
                    exc.message,
                )
                continue

            if is_response(message):
                self._resolve_response(message)
                continue

            await self._incoming.put(message)

        # 子进程结束：唤醒所有等待中的请求，避免永久挂起。
        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    MCPError("MCP 子进程已退出")
                )
        self._pending.clear()

    def _resolve_response(
        self,
        message: dict[str, Any],
    ) -> None:
        message_id = message.get("id")
        future = self._pending.get(message_id)

        if future is None or future.done():
            logger.debug(
                "mcp transport: 收到未知 id 的响应，忽略（id=%r）",
                message_id,
            )
            return

        future.set_result(message)

    async def _stderr_loop(self) -> None:
        process = self._process

        if process is None or process.stderr is None:
            return

        assert process.stderr is not None

        while True:
            try:
                raw = await process.stderr.readline()
            except Exception:  # noqa: BLE001
                break

            if not raw:
                break

            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")

            if not line:
                continue

            if self._stderr_handler is not None:
                self._stderr_handler(line)
            else:
                logger.info("mcp server stderr: %s", line)


__all__ = [
    "StdioClientTransport",
    "StdioServerTransport",
]
