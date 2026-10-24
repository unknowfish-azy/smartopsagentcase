from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionContext:
    """
    Agent 执行上下文。
    """

    request_id: str

    user_id: str

    environment: str = "default"

    dry_run: bool = False

    metadata: dict[str, Any] = field(
        default_factory=dict
    )