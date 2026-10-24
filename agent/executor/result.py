from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """
    单次工具执行结果。
    """

    success: bool

    tool_name: str

    message: str

    output: Any = None

    error: str | None = None

    duration_ms: int = 0

    metadata: dict[str, Any] = field(
        default_factory=dict
    )