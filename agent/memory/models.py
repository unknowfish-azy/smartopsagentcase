from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class MemoryItem:

    key: str

    value: Any

    memory_type: str = "short_term"

    created_at: str = field(
        default_factory=lambda:
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    # P2：归属隔离（用户/租户）。None 表示共享记忆。
    owner: str | None = None

    # P2：过期时间（相对 created_at 的秒数）。None 表示永不过期。
    ttl_seconds: int | None = None

    # P2：检索辅助标签
    tags: list[str] = field(default_factory=list)

    def _created(self) -> datetime:
        return datetime.fromisoformat(self.created_at)

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.ttl_seconds is None:
            return False
        now = now or datetime.now(timezone.utc)
        return now >= self._created() + timedelta(seconds=self.ttl_seconds)