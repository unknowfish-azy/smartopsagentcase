from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


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

    approval_id: str | None = None

    task_id: str | None = None

    # A context owns one run; replaying a step keeps its run correlation.
    run_id: str = field(default_factory=lambda: uuid4().hex)
