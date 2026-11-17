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

    # P3（蒸馏 AgentForge）：依赖的前置步骤 step_id 列表。
    # 空 = 无依赖；线性执行器忽略此字段，DAG 执行器按依赖调度。
    depends_on: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "description": self.description,
            "requires_approval": self.requires_approval,
            "depends_on": list(self.depends_on),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanStep":
        return cls(
            step_id=int(data["step_id"]),
            action=str(data.get("action", "")),
            tool_name=str(data["tool_name"]),
            arguments=dict(data.get("arguments") or {}),
            description=str(data.get("description", "")),
            requires_approval=bool(data.get("requires_approval", False)),
            depends_on=[int(x) for x in (data.get("depends_on") or [])],
        )