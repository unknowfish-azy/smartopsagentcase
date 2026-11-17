"""P1-3 故障案例向量检索 API Schema。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CaseRetrieveRequest(BaseModel):
    """Agent 把当前故障 symptom/analysis 丢过来，返回 top-k 历史案例。"""

    query: str = Field(..., min_length=1, description="故障描述（symptom 或 symptom+analysis 拼接）")
    top_k: int = Field(default=3, ge=1, le=10)
    include_lesson: bool = Field(default=True, description="返回历史教训（给 Agent 决策参考）")
    include_recommendation: bool = Field(default=True)


class RetrievedCase(BaseModel):
    rank: int
    score: float
    incident_key: str
    category: str
    severity: str
    symptom: str
    outcome: str
    lesson: str | None = None
    recommendation: str | None = None


class CaseRetrieveResponse(BaseModel):
    ok: bool = True
    mode: Literal["tinybert", "tfidf", "heuristic"]
    index_entries: int
    results: list[RetrievedCase]


class RetrieveModelInfo(BaseModel):
    available: bool
    kind: Literal["tinybert", "tfidf", "heuristic", "unavailable"]
    index_entries: int
    index_store_mode: Literal["faiss", "numpy", "none"]
    reason: str | None = None
