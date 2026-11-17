"""P0-2 根因定位 API 的 Schema。

Agent 调用 /api/nn/rootcause 时传关联告警图，返回 top-k 候选根因节点（排序后）。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AlertNode(BaseModel):
    """单条告警作为图节点。"""

    alert_id: str | int = Field(description="告警唯一 ID，返回结果时用来引用")
    severity: Literal["P0", "P1", "P2", "P3"] = "P2"
    status: Literal["OPEN", "PENDING_APPROVAL", "REMEDIATING", "CLOSED"] = "OPEN"
    metric: str | None = None
    server: str | None = None
    value: float | None = None


class AlertEdge(BaseModel):
    """节点间的关联边（对应 sentinel_alert_correlation_edge）。"""

    alert_a_id: str | int
    alert_b_id: str | int
    lift_score: float | None = Field(default=None, description="关联度（>1 正相关，越大越紧）")
    co_fires: int | None = Field(default=None, description="共同出现次数")
    correlation_type: Literal["TIME_WINDOW", "LIFT", "SAME_SERVER"] = "TIME_WINDOW"


class RootCauseRequest(BaseModel):
    """一个 correlation_event 对应一次根因分析。"""

    nodes: list[AlertNode] = Field(..., min_length=1, description="该 event 包含的所有告警节点")
    edges: list[AlertEdge] = Field(default_factory=list, description="节点间关联（可为空，走 heuristic）")
    top_k: int = Field(default=3, ge=1, le=10, description="返回 top-k 候选")
    event_id: str | None = None
    event_key: str | None = None
    detail: bool = Field(default=False, description="是否返回每个节点的 feature/debug")


class RootCauseCandidate(BaseModel):
    """一个候选根因节点。"""

    rank: int
    alert_id: str | int
    score: float
    severity: str | None = None
    metric: str | None = None
    server: str | None = None
    degree: int = Field(default=0, description="该节点在图里的边数（可解释辅助）")


class RootCauseResponse(BaseModel):
    ok: bool = True
    mode: Literal["pyg_gcn", "pytorch_gcn", "pyg_gat", "pytorch_gat", "heuristic"]
    model_status: Literal["ok", "unavailable"]
    event_id: str | None = None
    event_key: str | None = None
    total_nodes: int
    total_edges: int
    candidates: list[RootCauseCandidate]
    extra: dict[str, Any] = Field(default_factory=dict)


class RootCauseModelInfo(BaseModel):
    available: bool
    kind: Literal["pyg_gcn", "pytorch_gcn", "pyg_gat", "pytorch_gat", "heuristic", "unavailable"]
    reason: str | None = None
    torch_available: bool = False
    pyg_available: bool = False
    variant: Literal["gcn", "gat"] = "gcn"
    gat_attention_available: bool = False
    hidden_channels: int | None = None
    gat_heads: int | None = None
