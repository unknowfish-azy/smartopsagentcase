"""W7：事件驱动的内部触发入口（只读初诊）。

Sentinel 告警在 Java 侧落库后，通过内部令牌触发本接口：

1. **只读白名单**：工具固定为 ``sentinel.alerts`` / ``sentinel.metrics`` /
   ``knowledge.search``，steps 由服务端生成，请求体不接受任何 tools/steps；
2. **模型闸门**：模型不可用只记 WARN 并返回 ``created=false``，不产出事件；
3. **不编造**：计划未完成、或没有任何一步真实成功时，同样返回 ``created=false``；
4. **可审计**：真实执行过的 run 会经 ``RunLedgerRecorder`` 计入 ``agent_run``。

纠察事件的写回由 Java 完成（归属取告警所属用户），本接口只返回诊断结果。
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..core.config import settings
from ..services import model_probe
from ..services.agent_runtime import AgentRuntime, AgentRunResult
from ..services.run_ledger import RunLedgerRecorder

logger = logging.getLogger(__name__)

router = APIRouter()

# 固定只读白名单：任何写工具都不允许出现在触发链路里。
TRIGGER_READ_TOOLS = frozenset({"sentinel.alerts", "sentinel.metrics", "knowledge.search"})

_INTERNAL_HEADER = "X-SmartOps-Internal-Token"
_COMPLETED_STATUS = "completed"


class AgentTriggerRequest(BaseModel):
    """告警上下文（Java 内部调用传入；camelCase 与后端 DTO 对齐）。"""

    model_config = ConfigDict(populate_by_name=True)

    alert_id: int = Field(alias="alertId", ge=1)
    task_id: int | None = Field(default=None, alias="taskId")
    resource_key: str | None = Field(default=None, alias="resourceKey", max_length=191)
    owner_user_id: str | None = Field(default=None, alias="ownerUserId", max_length=64)
    severity: str | None = Field(default=None, max_length=32)
    metric: str | None = Field(default=None, max_length=128)
    observed: str | None = Field(default=None, max_length=256)
    threshold: str | None = Field(default=None, max_length=256)
    title: str | None = Field(default=None, max_length=200)
    server_id: int | None = Field(default=None, alias="serverId")
    source: str = Field(default="SENTINEL_ALERT", max_length=64)


def _require_internal_token(request: Request) -> None:
    """fail-closed：未配置令牌直接 503，缺失 401，不匹配 403。"""
    secret = str(getattr(settings, "memory_internal_token", "") or "")
    if not secret:
        raise HTTPException(status_code=503, detail="内部令牌未配置，拒绝触发")
    supplied = request.headers.get(_INTERNAL_HEADER, "")
    if not supplied:
        raise HTTPException(status_code=401, detail="缺少内部令牌")
    if not hmac.compare_digest(supplied, secret):
        raise HTTPException(status_code=403, detail="内部令牌不匹配")


def validate_tool_names(names: list[str]) -> None:
    """白名单校验：出现任何非只读工具立即拒绝。"""
    forbidden = [name for name in names if name not in TRIGGER_READ_TOOLS]
    if forbidden:
        raise HTTPException(status_code=400, detail=f"触发链路只允许只读工具：{forbidden}")


def build_trigger_steps(payload: AgentTriggerRequest) -> list[dict[str, Any]]:
    """服务端生成固定只读 steps（请求体无法注入工具或参数）。"""
    steps: list[dict[str, Any]] = []

    alert_args: dict[str, Any] = {}
    if payload.task_id is not None:
        alert_args["taskId"] = payload.task_id
    steps.append(
        {
            "step_id": 1,
            "tool_name": "sentinel.alerts",
            "action": "read",
            "arguments": alert_args,
            "description": "读取该巡检任务当前告警面",
        }
    )

    # Sentinel 任务没有服务器映射时跳过 metrics，绝不猜一个 serverId。
    if payload.server_id is not None:
        steps.append(
            {
                "step_id": len(steps) + 1,
                "tool_name": "sentinel.metrics",
                "action": "read",
                "arguments": {"serverId": payload.server_id},
                "description": "读取关联服务器最新指标",
            }
        )

    query = " ".join(
        part for part in (payload.title, payload.metric, payload.observed) if part
    ).strip()[:200]
    steps.append(
        {
            "step_id": len(steps) + 1,
            "tool_name": "knowledge.search",
            "action": "read",
            "arguments": {"query": query or "告警根因", "top_k": 5},
            "description": "检索处置知识与历史证据",
        }
    )

    validate_tool_names([step["tool_name"] for step in steps])
    return steps


def _goal(payload: AgentTriggerRequest) -> str:
    title = payload.title or f"告警 #{payload.alert_id}"
    detail = ""
    if payload.metric:
        detail = f"（{payload.metric}={payload.observed or '-'}）"
    return f"诊断哨兵告警：{title}{detail}"[:500]


def _read_tools() -> list[Any]:
    """只装配只读工具，并按白名单二次过滤（纵深防御）。"""
    from agent.tools.builtin import build_product_read_tools  # noqa: PLC0415

    tools = build_product_read_tools(
        token=str(getattr(settings, "knowledge_api_key", "") or "") or None,
        internal_token=str(getattr(settings, "memory_internal_token", "") or "") or None,
    )
    return [tool for tool in tools if getattr(tool, "name", "") in TRIGGER_READ_TOOLS]


def _run_diagnosis(payload: AgentTriggerRequest, runtime: AgentRuntime | None = None) -> AgentRunResult:
    """同步执行只读诊断；由端点放进线程池，避免阻塞事件循环。"""
    runtime = runtime or AgentRuntime(tools=_read_tools())
    return runtime.run(
        goal=_goal(payload),
        user_id=payload.owner_user_id or "system",
        page_context={
            "entity": "sentinel_alert",
            "alertId": payload.alert_id,
            "taskId": payload.task_id,
            "resourceKey": payload.resource_key,
        },
        steps=build_trigger_steps(payload),
    )


@router.post("/trigger")
async def trigger(payload: AgentTriggerRequest, request: Request) -> dict[str, Any]:
    """接收内部告警触发，执行只读初诊并返回结论（不写事件）。"""
    _require_internal_token(request)

    available, detail = await model_probe.probe_llm_availability()
    if not available:
        logger.warning(
            "agent_trigger.model_unavailable alert_id=%s reason=%s", payload.alert_id, detail
        )
        return {
            "created": False,
            "modelAvailable": False,
            "reason": "MODEL_UNAVAILABLE",
            "detail": detail,
        }

    result = await asyncio.to_thread(_run_diagnosis, payload)

    # 账本：只记录真实发生过的 run（未执行时上面已提前返回）。
    ledger = await RunLedgerRecorder().record(result, goal=_goal(payload))

    succeeded = any(bool(call.get("success")) for call in result.tool_calls)
    created = result.status == _COMPLETED_STATUS and succeeded
    if not created:
        logger.warning(
            "agent_trigger.no_event alert_id=%s status=%s succeeded=%s",
            payload.alert_id, result.status, succeeded,
        )

    return {
        "created": created,
        "modelAvailable": True,
        "runId": result.run_id,
        "status": result.status,
        "risk": result.risk,
        "answer": result.answer,
        "reason": result.reason,
        "brief": result.brief,
        "toolCalls": result.tool_calls,
        "ledger": ledger,
    }
