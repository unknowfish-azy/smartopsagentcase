from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeContext:
    """
    Agent运行时上下文。

    该对象不会保存敏感凭据。
    """

    request_id: str
    user_id: str | None = None
    role: str = "USER"
    environment: str = "default"
    dry_run: bool = True

    metadata: dict[str, Any] = field(default_factory=dict)

    def copy(self) -> "RuntimeContext":
        return RuntimeContext(
            request_id=self.request_id,
            user_id=self.user_id,
            role=self.role,
            environment=self.environment,
            dry_run=self.dry_run,
            metadata=dict(self.metadata),
        )