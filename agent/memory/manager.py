from .models import MemoryItem
from .short_term import ShortTermMemory
from .long_term import LongTermMemory


class MemoryManager:

    def __init__(
        self,
        short_term=None,
        long_term=None,
    ):
        self.short_term = (
            short_term
            or ShortTermMemory()
        )

        self.long_term = (
            long_term
            or LongTermMemory()
        )

    def remember(
        self,
        key: str,
        value,
        memory_type: str = "short_term",
        owner: str | None = None,
        ttl_seconds: int | None = None,
        tags: list[str] | None = None,
    ):
        """写入记忆；owner 用于用户/租户隔离，ttl_seconds 控制过期遗忘。"""

        item = MemoryItem(
            key=key,
            value=value,
            memory_type=memory_type,
            owner=owner,
            ttl_seconds=ttl_seconds,
            tags=tags or [],
        )

        if memory_type == "long_term":
            self.long_term.save(item)
        else:
            self.short_term.add(item)

        return item

    def recall(
        self,
        key: str,
        owner: str | None = None,
    ):
        """按键取回记忆；传入 owner 时启用隔离（看不到他人的私有记忆）。"""

        item = self.long_term.get(key, owner=owner)

        if item:
            return item

        for item in reversed(
            self.short_term.get_all()
        ):
            if item.key == key and not item.is_expired():
                if owner is None or item.owner is None or item.owner == owner:
                    return item

        return None

    def search(
        self,
        query: str,
        owner: str | None = None,
        top_k: int = 5,
    ):
        """语义/关键词混合检索长期记忆（P2）。"""

        return self.long_term.search(query, owner=owner, top_k=top_k)