"""N03 机制原型：自持有 loopback 服务的真实 socket transport。

冻结规则来源：
- ``docs/design/recovery-contract-v1/semantics.md`` §4.1（1 秒含连接+完整读取
  +解析的绝对时限）、§8.1（谓词输入契约）。
- 交接书 PROBE-P1-01 卡：仅自持有 loopback 服务、固定 GET 和登记端口；
  禁任意 URL/代理/重定向；响应体 ≤4KiB；整体绝对 deadline。

边界（有意如此）：
- 本模块只提供 ``Transport`` 实现，不改写 ``ProbeRequest`` 的任何字段；
  ``http.client`` 本身不跟随重定向、不走代理，重定向响应按原样上交，
  由 ``ProbeExecutor`` 记 ``REDIRECT_BLOCKED``。
- 绝对 deadline 用 ``time.monotonic`` 计算；进程重启后不比较旧单调时钟，
  run 级 deadline 由 ``RunBudget.deadline_at`` 持久化 ISO 时间承载。
"""

from __future__ import annotations

import http.client
import socket
import time
from datetime import datetime, timezone

from .probes import (
    PROBE_HOST,
    ExecutionResult,
    ProbeExecutionError,
    ProbeExecutor,
    ProbeRegistry,
    ProbeRequest,
    Transport,
    TransportResponse,
)


def utc_now() -> datetime:
    """采集墙钟（UTC）；单调性只用于 transport 内部 deadline，不外泄比较。"""
    return datetime.now(timezone.utc)


def loopback_transport() -> Transport:
    """构造真实 socket transport：仅 loopback、固定 GET、绝对时限内读完。

    - 连接、响应头、完整 body 读取共享同一个 ``request.timeout_ms`` 预算；
      每次阻塞读取前把 socket 超时裁剪为剩余预算，slow-drip 无法续命。
    - 最多读取 ``max_bytes + 1`` 字节，超限即停，由执行器判 MALFORMED。
    """

    def _send(request: ProbeRequest) -> TransportResponse:
        if request.host != PROBE_HOST:
            raise ProbeExecutionError(f"transport 只允许 loopback 主机：{request.host!r}")
        if request.follow_redirects or request.use_proxy:
            raise ProbeExecutionError("transport 不支持重定向或代理")
        if request.method != "GET":
            raise ProbeExecutionError(f"transport 只允许 GET：{request.method!r}")

        deadline = time.monotonic() + request.timeout_ms / 1000.0
        connection = http.client.HTTPConnection(
            request.host, request.port, timeout=request.timeout_ms / 1000.0
        )
        try:
            connection.connect()
            sock = connection.sock
            if sock is None:  # pragma: no cover - 防御：connect 成功后必有 sock
                raise ProbeExecutionError("连接未建立")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("连接已耗尽单探针绝对时限")
            sock.settimeout(remaining)
            connection.putrequest("GET", request.path, skip_accept_encoding=True)
            connection.endheaders()
            response = connection.getresponse()
            # Python 3.14 起 getresponse() 会把 connection.sock 置 None
            # （socket 所有权移交给 response）；继续用连接时捕获的引用。

            body = bytearray()
            cap = request.max_bytes + 1
            while len(body) < cap:
                # Python 3.14 的 HTTPResponse 在读完 body 后会自动关闭底层
                # socket；已关闭则读取结束，不得再触碰旧 socket 引用。
                if response.isclosed():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("读取超过单探针绝对时限")
                sock.settimeout(remaining)
                chunk = response.read1(cap - len(body))
                if not chunk:
                    break
                body.extend(chunk)

            headers = {str(key): str(value) for key, value in response.getheaders()}
            return TransportResponse(
                status_code=response.status,
                body=bytes(body),
                headers=headers,
            )
        except socket.timeout as exc:
            # socket.timeout 在 Python 3.10+ 是 TimeoutError 别名；显式统一。
            raise TimeoutError("单探针绝对时限到期") from exc
        finally:
            connection.close()

    return _send


class LoopbackProbeClient:
    """机制原型客户端：登记表 + 真实 loopback transport 的有界执行器。

    只接受 ``ProbeRegistry`` 中已登记的 probe_id；预算记账由调用方
    （``RunBudget.record_call``）在每次实际执行后完成，重试同样计费。
    """

    def __init__(self, registry: ProbeRegistry) -> None:
        if not isinstance(registry, ProbeRegistry):
            raise ProbeExecutionError("registry 必须是 ProbeRegistry")
        self._registry = registry
        self._executor = ProbeExecutor(transport=loopback_transport(), clock=utc_now)

    def execute(
        self,
        probe_id: str,
        *,
        run_deadline_at: datetime | str | None = None,
    ) -> ExecutionResult:
        return self._executor.execute(
            self._registry.get(probe_id), run_deadline_at=run_deadline_at
        )


__all__ = ["LoopbackProbeClient", "loopback_transport", "utc_now"]
