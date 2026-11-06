"""PERF-02：AI 服务共享 HTTP transport 与上游并发闸门。

原实现（rag.py、llm.py、model_gateway.py）在每次上游调用里新建
`httpx.AsyncClient`：连接无法复用、握手次数随请求线性增长，也没有任何并发上限，
上游变慢时请求会无界堆积。

这里由 FastAPI lifespan 启动一个进程级共享客户端：

* 连接池上限、保活连接数和池等待时间来自配置；
* 一个 asyncio 信号量作为并发闸门，排队超过 `http_queue_timeout` 就抛
  `UpstreamSaturated`（明确的过载响应），而不是继续堆积；
* 凭据与上下文仍由调用方逐请求传入（headers/task_id/run_id），
  共享 client 上不保存任何用户态数据，因此请求之间不会串号。

没有经过 lifespan 的场景（单元测试直接调用 service）按请求临时创建客户端，
行为与改造前一致，也不会伪造"共享池已生效"的统计。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import AsyncIterator

import httpx

from . import metrics
from .config import settings
from .exceptions import UpstreamSaturated


class HttpPool:
    """共享 AsyncClient + 并发闸门；计数均为真实观测值。"""

    def __init__(
        self,
        *,
        max_connections: int | None = None,
        max_keepalive_connections: int | None = None,
        max_concurrent_requests: int | None = None,
        queue_timeout: float | None = None,
        pool_timeout: float | None = None,
        request_timeout: float | None = None,
    ) -> None:
        self.max_connections = max(1, max_connections or settings.http_max_connections)
        self.max_keepalive_connections = max(
            1, max_keepalive_connections or settings.http_max_keepalive_connections
        )
        self.max_concurrent_requests = max(
            1, max_concurrent_requests or settings.http_max_concurrent_requests
        )
        self.queue_timeout = queue_timeout if queue_timeout is not None else settings.http_queue_timeout
        self.pool_timeout = pool_timeout if pool_timeout is not None else settings.http_pool_timeout
        self.request_timeout = request_timeout or settings.request_timeout
        self._client: httpx.AsyncClient | None = None
        self._gate: asyncio.Semaphore | None = None
        self.client_creations = 0
        self.in_flight = 0
        self.saturated = 0
        self.gate_waits = 0

    async def startup(self) -> None:
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.request_timeout, pool=self.pool_timeout),
            trust_env=False,
            limits=httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_keepalive_connections,
            ),
        )
        self._gate = asyncio.Semaphore(self.max_concurrent_requests)
        self._count_creation()

    async def shutdown(self) -> None:
        client = self._client
        self._client = None
        self._gate = None
        if client is not None:
            await client.aclose()

    @contextlib.asynccontextmanager
    async def acquire(self, *, timeout: float | None = None) -> AsyncIterator[httpx.AsyncClient]:
        """借出一个客户端；共享池未启动时按请求临时创建（保持既有测试语义）。"""
        client = self._client
        gate = self._gate
        if client is None or gate is None:
            async with httpx.AsyncClient(
                timeout=timeout or self.request_timeout,
                trust_env=False,
            ) as fallback:
                self._count_creation()
                yield fallback
            return

        started = time.perf_counter()
        try:
            await asyncio.wait_for(gate.acquire(), timeout=self.queue_timeout)
        except asyncio.TimeoutError:
            self.saturated += 1
            metrics.HTTP_POOL_SATURATED.labels(metrics.SERVICE).inc()
            raise UpstreamSaturated(
                f"上游并发已达上限 {self.max_concurrent_requests}，"
                f"排队 {self.queue_timeout:.1f}s 仍未取得执行名额"
            )
        finally:
            waited = time.perf_counter() - started
            self.gate_waits += 1
            metrics.HTTP_POOL_GATE_WAIT.labels(metrics.SERVICE).observe(waited)

        self.in_flight += 1
        metrics.HTTP_POOL_IN_FLIGHT.labels(metrics.SERVICE).set(self.in_flight)
        try:
            yield client
        finally:
            self.in_flight -= 1
            metrics.HTTP_POOL_IN_FLIGHT.labels(metrics.SERVICE).set(self.in_flight)
            gate.release()

    def snapshot(self) -> dict[str, int | float | bool]:
        return {
            "shared": self._client is not None,
            "clientCreations": self.client_creations,
            "inFlight": self.in_flight,
            "saturated": self.saturated,
            "gateWaits": self.gate_waits,
            "maxConnections": self.max_connections,
            "maxConcurrentRequests": self.max_concurrent_requests,
            "queueTimeoutSeconds": self.queue_timeout,
        }

    def _count_creation(self) -> None:
        self.client_creations += 1
        metrics.HTTP_POOL_CLIENT_CREATIONS.labels(metrics.SERVICE).inc()


http_pool = HttpPool()

__all__ = ["HttpPool", "http_pool"]
