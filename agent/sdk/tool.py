from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from agent.policies.risk import RiskLevel


@dataclass
class ToolDefinition:
    name: str
    description: str
    risk: RiskLevel = RiskLevel.LOW


class PluginTool(ABC):

    definition: ToolDefinition

    @abstractmethod
    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> Any:
        raise NotImplementedError