from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolMetadata:

    name: str

    description: str

    risk_level: str = "LOW"

    requires_approval: bool = False

    parameters: dict[str, Any] = field(
        default_factory=dict
    )