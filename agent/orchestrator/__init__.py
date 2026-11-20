"""P3 多 Agent 协同调度。"""

from .models import (
    AgentProfile,
    AgentSpecialty,
    SubTask,
    SubTaskResult,
    OrchestrationPlan,
)
from .orchestrator import Orchestrator, OrchestratorPolicy
from .dispatcher import decompose_goal
from .presets import ALL_PRESET_AGENTS, SPECIALTY_INDEX

__all__ = [
    "AgentProfile",
    "AgentSpecialty",
    "SubTask",
    "SubTaskResult",
    "OrchestrationPlan",
    "Orchestrator",
    "OrchestratorPolicy",
    "decompose_goal",
    "ALL_PRESET_AGENTS",
    "SPECIALTY_INDEX",
]
