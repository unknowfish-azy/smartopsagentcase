"""PERF-08：AI 服务的指标出口。

原先 Prometheus 配置里声明了 `ai-service:8001/metrics`，但服务从未暴露该路径，
抓取任务长期是 404 —— 面板上看不到数据，却也不报错。这里补上真实可抓取的指标：

* 请求计数（含状态码），用于 QPS / 错误率看板；
* 请求耗时直方图，用于 P95/P99；
* 构建版本信息，用于确认"跑的是哪个版本"。

指标来源是中间件实测，不构造任何假数据。
"""

from __future__ import annotations

import time

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

SERVICE = "smartops-ai-service"

REQUEST_COUNT = Counter(
    "smartops_ai_http_requests_total",
    "AI 服务 HTTP 请求数",
    ["service", "method", "path", "status"],
)

REQUEST_DURATION = Histogram(
    "smartops_ai_http_request_duration_seconds",
    "AI 服务 HTTP 请求耗时",
    ["service", "method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

BUILD_INFO = Gauge(
    "smartops_ai_build_info",
    "AI 服务构建信息（恒为 1，版本在标签里）",
    ["service", "version"],
)


def mark_build(version: str) -> None:
    BUILD_INFO.labels(SERVICE, version).set(1)


def _path_for(request: Request) -> str:
    """优先使用路由模板，避免把具体 ID 写进标签造成基数爆炸。"""
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template or request.url.path


async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    started = time.perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        path = _path_for(request)
        REQUEST_COUNT.labels(SERVICE, request.method, path, status).inc()
        REQUEST_DURATION.labels(SERVICE, request.method, path).observe(time.perf_counter() - started)


async def metrics_endpoint() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
