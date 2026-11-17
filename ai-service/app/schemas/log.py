"""P1-2 日志分类前置过滤 API Schema。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VALID_LABELS = Literal[
    "oom", "timeout", "disk_full", "connection_refused",
    "process_crash", "auth_error", "network_error", "noise",
]


class LogItem(BaseModel):
    """单条待分类日志。"""

    text: str = Field(..., min_length=1, description="日志原文")
    source: str | None = None
    timestamp: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class LogClassifyRequest(BaseModel):
    """批量分类——Agent 把一批原始日志丢进来，服务端分类 + 过滤 noise。"""

    logs: list[LogItem] = Field(..., min_length=1, description="待分类日志列表")
    filter_noise: bool = Field(
        default=True,
        description="是否过滤掉 noise 类（前置过滤的核心功能——Agent 只处理非 noise 的）",
    )
    min_confidence: float = Field(default=0.3, ge=0.0, le=1.0)


class TopLabelItem(BaseModel):
    label: str
    confidence: float


class LogLabelResult(BaseModel):
    """单条日志的分类结果。"""

    label: str
    confidence: float
    is_noise: bool
    top_labels: list[TopLabelItem] = Field(
        default_factory=list,
        description="top-3 标签概率分布，方便 Agent 理解模型有多大把握",
    )
    should_keep: bool = Field(
        default=True,
        description="filter_noise=True 时：False 表示这条被过滤掉",
    )


class LogClassifyResponse(BaseModel):
    ok: bool = True
    mode: Literal["tinybert", "textcnn", "heuristic"]
    num_total: int
    num_kept: int
    num_filtered_noise: int
    results: list[LogLabelResult]
    label_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="所有日志的标签分布统计（Agent 用来做告警聚合）",
    )


class LogModelInfo(BaseModel):
    available: bool
    kind: Literal["tinybert", "textcnn", "heuristic", "unavailable"]
    variant: Literal["tinybert", "textcnn", "heuristic"] = "heuristic"
    reason: str | None = None
    torch_available: bool = False
    transformers_available: bool = False
    num_labels: int = 8
