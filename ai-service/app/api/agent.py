"""统一 Agent 执行入口。

与 ``/api/chat`` 共用同一套边缘身份校验（X-Run-Token）：
没有可验证的调用方就不允许进入工具执行链。

- ``POST /api/agent/run`` 同步返回一次 run 的结果
- ``steps`` 为空时交给 ReAct 规划器边执行边观察；
- ``steps`` 显式给出时按计划执行，便于回放与审批。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..services.agent_runtime import AgentRuntime
from ..services.run_ledger import RunLedgerRecorder

from .chat import require_chat_identity

logger = logging.getLogger(__name__)

router = APIRouter()

# 只透传身份相关头；产品接口按当前用户会话鉴权，禁止用系统账号替代。
_FORWARDED_HEADERS = (
    "cookie",
    "authorization",
    "x-run-token",
    "x-api-key",
    "x-xsrf-token",
    "x-csrf-token",
)


def _forwarded_headers(request: Request) -> dict[str, str]:
    return {
        name: request.headers[name]
        for name in _FORWARDED_HEADERS
        if name in request.headers
    }


class AgentStepSpec(BaseModel):
    """一步工具调用（工具名、动作、参数）。"""

    step_id: int | None = None
    tool_name: str = Field(min_length=1, max_length=128)
    action: str = Field(default="", max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    description: str = Field(default="", max_length=500)
    requires_approval: bool = False


class AgentRunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    steps: list[AgentStepSpec] = Field(default_factory=list)
    user_id: str = Field(default="", max_length=64)
    request_id: str | None = Field(default=None, max_length=128)
    approval_id: str | None = Field(default=None, max_length=128)
    dry_run: bool = False
    page_context: dict[str, Any] = Field(default_factory=dict)
    max_iterations: int = Field(default=6, ge=1, le=12)


@router.post("/run")
async def run_agent(
    payload: AgentRunRequest,
    request: Request,
    identity: dict | None = Depends(require_chat_identity),
) -> dict[str, Any]:
    """执行一次 Agent run；输入/输出闸门与工具执行都由 AgentRuntime 负责。"""
    user_id = payload.user_id or (identity or {}).get("subject") or "anonymous"
    steps = [
        step.model_dump(exclude_none=True)
        for step in payload.steps
    ]
    if steps:
        # PlanStep.step_id 必填，缺省按顺序补全。
        for index, step in enumerate(steps, start=1):
            step.setdefault("step_id", index)

    # 延迟导入：agent_runtime 在导入时已把仓库根加入 sys.path。
    from agent.tools.builtin import (  # noqa: PLC0415
        build_product_action_tools,
        build_product_read_tools,
    )

    runtime = AgentRuntime(
        tools=build_product_read_tools() + build_product_action_tools()
    )
    result = await asyncio.to_thread(
        runtime.run,
        goal=payload.goal,
        user_id=user_id,
        request_id=payload.request_id,
        steps=steps or None,
        dry_run=payload.dry_run,
        approval_id=payload.approval_id,
        page_context=payload.page_context,
        max_iterations=payload.max_iterations,
        forwarded_headers=_forwarded_headers(request),
    )
    body = result.to_dict()
    # Trust Ledger：回传真实结果；未配置内部通道时只降级，不影响 run 返回。
    body["metadata"]["ledger"] = await RunLedgerRecorder().record(result, goal=payload.goal)
    return body


@router.get("/audit/verify")
async def verify_audit_chain(
    identity: dict | None = Depends(require_chat_identity),
) -> dict[str, Any]:
    """校验审计哈希链完整性（一键验链）。

    返回 ``verify_all()`` 的真实字段；基线未启用时明确标记不可用，
    不返回任何"看起来通过"的占位结论。
    """
    from ..core.baseline import get_bundle  # noqa: PLC0415 - 延迟导入避免启动期耦合

    checked_at = datetime.now(timezone.utc).isoformat()
    bundle = get_bundle()
    if bundle is None:
        return {
            "available": False,
            "ok": False,
            "reason": "安全基线未启用或装配失败",
            "checkedAt": checked_at,
        }
    report = bundle.verify_audit_chain()
    return {"available": True, "checkedAt": checked_at, **report}
