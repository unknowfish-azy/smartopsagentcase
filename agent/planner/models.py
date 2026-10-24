from dataclasses import dataclass, field

from .steps import PlanStep


@dataclass
class AgentPlan:

    request_id: str

    goal: str

    steps: list[PlanStep] = field(
        default_factory=list
    )

    requires_human_approval: bool = False