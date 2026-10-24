from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanStep:

    step_id: int

    action: str

    tool_name: str

    arguments: dict[str, Any] = field(
        default_factory=dict
    )

    description: str = ""

    requires_approval: bool = False