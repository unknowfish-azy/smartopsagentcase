"""P2-1 处置动作效果预测 API Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VALID_ACTIONS = Literal[
    "restart", "scale_out", "scale_in", "rollback",
    "config_change", "code_fix", "manual_cleanup", "wait_and_observe",
]
VALID_CATEGORIES = Literal[
    "oom", "timeout", "disk_full", "connection_refused",
    "process_crash", "auth_error", "network_error", "other",
]
VALID_SEVERITIES = Literal["P0", "P1", "P2", "P3"]


class ActionEffectRequest(BaseModel):
    """Agent 给一个故障场景 + 候选动作，预测效果。"""

    category: VALID_CATEGORIES
    severity: VALID_SEVERITIES = "P2"
    actions: list[VALID_ACTIONS] = Field(
        ..., min_length=1, max_length=10,
        description="候选动作列表，服务端批量预测并排序",
    )


class ActionEffectResult(BaseModel):
    action: str
    success_prob: float      # 越高越好（能解决问题的概率）
    secondary_risk: float    # 越低越好（引发次生故障的概率）
    risk_score: float        # 综合 = (1 - success) + risk，越小越安全


class ActionEffectResponse(BaseModel):
    ok: bool = True
    mode: Literal["mlp", "heuristic"]
    category: str
    severity: str
    results: list[ActionEffectResult]


class ActionEffectModelInfo(BaseModel):
    available: bool
    kind: Literal["mlp", "heuristic", "unavailable"]
    reason: str | None = None
