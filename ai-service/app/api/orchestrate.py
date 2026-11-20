"""阶段 0：多子智能体编排的服务入口。

提供同步与 SSE 两种调用方式，内部复用 agent/orchestrator 的
「拆解 → 匹配 → 分波并发 → 整合」链路：

- ``POST /api/orchestrate``      同步返回完整计划与各子 Agent 结论
- ``GET  /api/orchestrate/stream`` SSE 推送 started / subtask_finished / finished

安全约定：默认只允许本机访问；配置了内部令牌后，远程可用
``X-Internal-Token`` 访问。子 Agent 的工具白名单仍在 DirectExecutor 内强制校验。
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# agent 包在仓库根目录，ai-service 运行时需要显式加入 sys.path。
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.kernel.event.bus import EventBus  # noqa: E402
from agent.kernel.event.events import (  # noqa: E402
    ORCHESTRATION_FINISHED,
    ORCHESTRATION_STARTED,
    ORCHESTRATION_SUBTASK_FINISHED,
    ORCHESTRATION_SUBTASK_STARTED,
)
from agent.orchestrator.orchestrator import Orchestrator, OrchestratorPolicy  # noqa: E402

from ..core.config import settings  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter()

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
_executor: Any | None = None
_executor_lock = threading.Lock()


class OrchestrateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)
    enable_agents: list[str] | None = None
    exclude_agents: list[str] | None = None
    max_concurrency: int | None = Field(default=None, ge=1, le=8)


def _guard(request: Request) -> None:
    """本机放行；跨机访问需要匹配内部令牌。"""
    secret = str(getattr(settings, "memory_internal_token", "") or "")
    token = request.headers.get("X-Internal-Token", "")
    if secret and token and hmac.compare_digest(token, secret):
        return
    host = request.client.host if request.client else ""
    if host in _LOCAL_HOSTS:
        return
    if bool(getattr(settings, "chat_allow_anonymous", False)):
        return
    raise HTTPException(status_code=403, detail="orchestrate 仅允许本机访问，跨机请配置 X-Internal-Token")


def _direct_executor() -> Any:
    """复用同一个 DirectExecutor：服务层无状态，避免重复加载模型。"""
    global _executor
    if _executor is not None:
        return _executor
    with _executor_lock:
        if _executor is None:
            from agent.orchestrator.direct_executor import DirectExecutor

            _executor = DirectExecutor()
    return _executor


def _build_orchestrator(bus: EventBus, max_concurrency: int | None) -> Orchestrator:
    policy = OrchestratorPolicy(
        max_concurrency=max(1, min(8, max_concurrency or 3)),
    )
    return Orchestrator(event_bus=bus, mode="direct", executor=_direct_executor(), policy=policy)


@router.post("")
async def orchestrate(payload: OrchestrateRequest, request: Request) -> dict[str, Any]:
    """同步执行一次多子智能体协同。"""
    _guard(request)
    try:
        orchestrator = _build_orchestrator(EventBus(), payload.max_concurrency)
        plan = await asyncio.to_thread(
            orchestrator.orchestrate,
            payload.goal,
            payload.context,
            payload.enable_agents,
            payload.exclude_agents,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 入口统一转 503，细节进日志
        logger.exception("orchestrate.failed")
        raise HTTPException(status_code=503, detail=f"编排不可用: {exc}") from exc
    return plan.to_dict()


def _parse_context(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="context 必须是合法 JSON") from exc
    return parsed if isinstance(parsed, dict) else {}


@router.get("/stream")
async def orchestrate_stream(
    request: Request,
    goal: str,
    context: str | None = None,
    enable_agents: str | None = None,
    exclude_agents: str | None = None,
    max_concurrency: int | None = None,
) -> StreamingResponse:
    """SSE 推送编排进度：started → subtask_finished×N → finished → result。"""
    _guard(request)
    if not goal.strip():
        raise HTTPException(status_code=422, detail="goal 不能为空")

    parsed_context = _parse_context(context)
    enabled = [item for item in (enable_agents or "").split(",") if item] or None
    excluded = [item for item in (exclude_agents or "").split(",") if item] or None

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    bus = EventBus()

    async def forward(event: Any) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {
                "event": event.name,
                "trace_id": event.request_id,
                "payload": event.payload,
                "at": event.created_at.isoformat(),
            },
        )

    for name in (
        ORCHESTRATION_STARTED,
        ORCHESTRATION_SUBTASK_STARTED,
        ORCHESTRATION_SUBTASK_FINISHED,
        ORCHESTRATION_FINISHED,
    ):
        bus.subscribe(name, forward)

    orchestrator = _build_orchestrator(bus, max_concurrency)

    async def runner() -> None:
        try:
            plan = await asyncio.to_thread(
                orchestrator.orchestrate, goal, parsed_context, enabled, excluded
            )
            loop.call_soon_threadsafe(
                queue.put_nowait, {"event": "result", "payload": plan.to_dict()}
            )
        except Exception as exc:  # noqa: BLE001 - 以 error 事件结束，不中断连接
            logger.exception("orchestrate.stream.failed")
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"event": "error", "payload": {"message": f"{type(exc).__name__}: {exc}"}},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    task = asyncio.create_task(runner())

    async def events() -> AsyncIterator[str]:
        try:
            yield "event: open\ndata: {}\n\n"
            while True:
                item = await queue.get()
                if item is None:
                    break
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            yield "event: close\ndata: {}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
