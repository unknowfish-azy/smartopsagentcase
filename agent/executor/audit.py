from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class AuditRecord:
    """
    Agent 执行审计记录。
    """

    request_id: str

    user_id: str

    tool_name: str

    action: str

    success: bool

    timestamp: str

    risk_level: str

    output: Any = None

    error: str | None = None

    @classmethod
    def create(
        cls,
        request_id: str,
        user_id: str,
        tool_name: str,
        action: str,
        success: bool,
        risk_level: str,
        output: Any = None,
        error: str | None = None,
    ):

        return cls(
            request_id=request_id,
            user_id=user_id,
            tool_name=tool_name,
            action=action,
            success=success,
            timestamp=datetime.now(
                timezone.utc
            ).isoformat(),
            risk_level=risk_level,
            output=output,
            error=error,
        )

    def to_dict(self):
        return asdict(self)