"""P2-3 策略自优化反思 API Schema。

Agent 处置完一个故障后调这个，把本次决策循环（symptom → rootcause → action → outcome → lesson）
append 进 P1-3 的 faiss 案例库，下次类似故障就能检索到。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VALID_CATEGORIES = Literal[
    "oom", "timeout", "disk_full", "connection_refused",
    "process_crash", "auth_error", "network_error", "other",
]
VALID_OUTCOMES = Literal["resolved", "mitigated", "failed", "pending"]
VALID_SEVERITIES = Literal["P0", "P1", "P2", "P3"]


class LearnFromIncidentRequest(BaseModel):
    """Agent 处置完后上报的一条完整决策循环。

    反思逻辑（service 层处理）：
    - outcome='failed' / 'pending' → 自动生成 lesson 草稿（"本次 XX 动作失败..."）
    - 缺 recommendation → 从 action + outcome 反推一个
    - incident_key 已存在 → 跳过（不重复 append）
    """

    # 唯一标识（可选但推荐）；给了就能防重复
    incident_key: str | None = Field(default=None, description="唯一 incident 号；不传则自动生成")
    category: VALID_CATEGORIES = Field(..., description="故障类别")
    severity: VALID_SEVERITIES = "P2"

    # 故障描述（symptom + analysis 用于 embedding）
    symptom: str = Field(..., min_length=5, description="故障表象（Agent 初始观察到的现象）")
    analysis: str | None = Field(default=None, description="根因分析（Agent 事后复盘结论）")

    # 处置
    action_taken: str = Field(..., min_length=2, description="最终执行的动作（restart / scale_out / rollback ...）")
    outcome: VALID_OUTCOMES = Field(..., description="处置结果")
    duration_minutes: int | None = Field(default=None, ge=0, le=1440, description="处置耗时")

    # 反思产物（可以不传——service 会根据 outcome 自动生成草稿）
    lesson: str | None = Field(default=None, description="处置教训；不传则按 outcome 自动生成")
    recommendation: str | None = Field(default=None, description="下次遇到类似故障的建议动作")


class LearnFromIncidentResponse(BaseModel):
    """append 结果 + 反思报告。"""

    ok: bool = True
    mode: Literal["learned", "skipped_duplicate", "partial"]
    reason: str | None = None

    index_size: int = Field(description="learn 后 faiss 案例库总条数")
    added_incident_key: str
    category: str
    outcome: str

    # 反思报告
    review: dict = Field(
        default_factory=dict,
        description=(
            "反思过程产出：\n"
            "  {reflection_quality: good/mediocre/weak,\n"
            "   auto_lesson: str | None (service 生成的 lesson 草稿),\n"
            "   auto_recommendation: str | None,\n"
            "   signals: list[str] (从 outcome/symptom 里抽的关键信号词)}"
        ),
    )


class LearnHistoryRequest(BaseModel):
    """查 learn 历史。"""

    limit: int = Field(default=20, ge=1, le=200)
    category: str | None = None
    outcome: str | None = None


class LearnHistoryResponse(BaseModel):
    total: int
    entries: list[dict]


class LearnModelInfo(BaseModel):
    available: bool = True
    index_entries: int = 0
    action_history_entries: int = 0
    faiss_mode: Literal["faiss", "numpy", "unavailable"] = "faiss"
    store_path: str | None = None
