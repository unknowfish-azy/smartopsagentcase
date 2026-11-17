"""P3 多 Agent 协同调度 —— Agent Profile 数据模型。

核心概念：每个子 Agent 有独立的专长（specialty）、独立的 system prompt、
独立的工具白名单、独立的状态上下文。**不共享 memory**，避免伪多 Agent。

Orchestrator 做三件事：
  1. 从 goal 拆出 SubTask 列表
  2. 按 specialty 匹配 AgentProfile
  3. 并发执行 + 结果整合 + 冲突检测
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class AgentSpecialty(str, Enum):
    """子 Agent 专长。用于任务分发匹配。

    - anomaly_sleuth:    看时序 → 挑异常片段 → 标疑似 metric
    - rootcause_hunter:  根因定位 → GCN 图模型 / 因果推断
    - log_interpreter:   日志分类 → noise 过滤 + 8 类故障标签
    - case_retriever:    向量检索 → 历史故障案例（P1-3 faiss）
    - action_advisor:    处置效果预测 → 推荐最安全动作（P2-1 MLP）
    - simulator:         故障仿真 → 合成序列 + 检测器验证（P2-2）
    - reflection:        反思学习 → 处置后 append 新案例（P2-3）
    - orchestrator:      协调者自己（不执行子任务）
    """

    ANOMALY_SLEUTH = "anomaly_sleuth"
    ROOTCAUSE_HUNTER = "rootcause_hunter"
    LOG_INTERPRETER = "log_interpreter"
    CASE_RETRIEVER = "case_retriever"
    ACTION_ADVISOR = "action_advisor"
    SIMULATOR = "simulator"
    REFLECTION = "reflection"
    ORCHESTRATOR = "orchestrator"


@dataclass
class AgentProfile:
    """子 Agent 注册信息。

    每个 Agent 有独立的 system_prompt + tool_names 白名单。
    这是避免"伪多 Agent"的关键——每个 Agent 真的只有自己的专长。
    """

    agent_id: str
    name: str
    specialty: AgentSpecialty
    system_prompt: str
    tool_names: list[str] = field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "specialty": self.specialty.value,
            "description": self.description,
            "tool_names": list(self.tool_names),
        }


@dataclass
class SubTask:
    """Orchestrator 从 goal 拆出的一个子任务。"""

    task_id: str
    description: str
    required_specialty: AgentSpecialty
    priority: int = 2  # 1=high 2=normal 3=low
    depends_on: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "specialty": self.required_specialty.value,
            "priority": self.priority,
            "depends_on": list(self.depends_on),
        }


@dataclass
class SubTaskResult:
    """子 Agent 完成一个子任务的产出。"""

    task_id: str
    agent_id: str
    success: bool
    summary: str = ""
    findings: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "success": self.success,
            "summary": self.summary,
            "findings": self.findings,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class OrchestrationPlan:
    """Orchestrator 完整闭环的计划 + 结果。"""

    goal: str
    subtasks: list[SubTask] = field(default_factory=list)
    results: list[SubTaskResult] = field(default_factory=list)
    conflict_notes: list[str] = field(default_factory=list)
    overall_status: Literal["completed", "partial", "failed"] = "completed"
    final_synthesis: str = ""

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "overall_status": self.overall_status,
            "subtasks": [t.to_dict() for t in self.subtasks],
            "results": [r.to_dict() for r in self.results],
            "conflict_notes": self.conflict_notes,
            "final_synthesis": self.final_synthesis,
        }
