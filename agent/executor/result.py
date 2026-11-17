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

    # 错误分类（ToolErrorCategory 值），失败时由 Executor 标注
    error_category: str | None = None

    duration_ms: int = 0

    metadata: dict[str, Any] = field(
        default_factory=dict
    )