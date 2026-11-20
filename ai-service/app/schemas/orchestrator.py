"""P3 多 Agent 协同调度 Schema。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class OrchestrateRequest(BaseModel):
    """Orchestrator 协同调度请求。

    输入：goal + context（时序数据、日志、图等）
    可选：enable_agents / exclude_agents 精细控制

    Context 字段（按需传，DirectExecutor 各 Agent 按需读取）：
      - values: list[float]          # 时序数据（AnomalySleuth）
      - calibration: list[float]     # 校准段（AnomalySleuth）
      - metric_name: str             # 指标名
      - logs: list[str]              # 日志（LogInterpreter）
      - category: str                # 故障类别（ActionAdvisor / Simulator / Reflection）
      - severity: str                # P0/P1/P2/P3
      - query: str                   # CaseRetriever query（不传则从 goal 拼）
      - actions: list[str]           # 候选动作
      - symptom / action_taken / outcome / lesson / recommendation  # Reflection 用
    """

    goal: str = Field(..., min_length=5, description="协同目标（自然语言）")
    context: dict[str, Any] = Field(default_factory=dict, description="子 Agent 共享上下文")
    enable_agents: list[str] | None = Field(default=None, description="只启用这些 agent_id")
    exclude_agents: list[str] | None = Field(default=None, description="排除这些 agent_id")
    max_concurrency: int = Field(default=3, ge=1, le=10)
    task_timeout_seconds: float | None = Field(
        default=None, gt=0, description="单波子任务时间预算（秒），不传用服务默认值"
    )
    max_task_retries: int | None = Field(
        default=None, ge=0, le=5, description="子任务异常后的额外重试次数"
    )
    mode: Literal["direct", "http"] = "direct"


class OrchestrateResponse(BaseModel):
    goal: str
    overall_status: Literal["completed", "partial", "failed"]
    subtasks: list[dict[str, Any]] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)
    conflict_notes: list[str] = Field(default_factory=list)
    final_synthesis: str = ""
    agent_count: int = 0
    trace_id: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)


class OrchestratorModelInfo(BaseModel):
    available: bool = True
    mode: Literal["direct", "http", "unavailable"] = "direct"
    agents: list[dict[str, Any]] = Field(default_factory=list)
    max_concurrency: int = 3
