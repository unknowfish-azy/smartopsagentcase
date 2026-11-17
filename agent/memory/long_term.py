from .models import MemoryItem
from .retrieval import HybridRetriever


class LongTermMemory:
    """长期记忆（P2 升级）：

    * TTL 遗忘：过期记忆在写入/检索时自动清除，防止脏记忆反复被召回；
    * 归属隔离：owner 不匹配的记忆不可见（None 为共享记忆）；
    * 混合检索：关键词 + 向量（注入 Embedder 后启用）；
    * 容量压缩：超过容量时淘汰最旧条目，可注入 summarizer 合并为摘要。
    存储仍为内存 dict，接口不变，后续可平替 Redis / MySQL / Vector DB。
    """

    def __init__(
        self,
        embedder=None,
        max_items: int = 1000,
        summarizer=None,
    ):
        self.storage: dict[str, MemoryItem] = {}
        self.embedder = embedder
        self.max_items = max_items
        self.summarizer = summarizer

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save(self, item: MemoryItem):
        self.purge_expired()
        self.storage[item.key] = item
        self._enforce_capacity()
        return item

    def get(self, key: str, owner: str | None = None):
        item = self.storage.get(key)
        if item is None or item.is_expired():
            return None
        if not self._visible(item, owner):
            return None
        return item

    def delete(self, key: str):
        self.storage.pop(key, None)

    def clear(self):
        self.storage.clear()

    # ------------------------------------------------------------------
    # 遗忘 / 隔离 / 压缩
    # ------------------------------------------------------------------

    def purge_expired(self) -> int:
        """清除过期记忆，返回清除数量。"""

        expired = [key for key, item in self.storage.items() if item.is_expired()]
        for key in expired:
            self.storage.pop(key, None)
        return len(expired)

    def _visible(self, item: MemoryItem, owner: str | None) -> bool:
        if item.owner is None:
            return True  # 共享记忆所有人可见
        return owner is not None and item.owner == owner

    def _enforce_capacity(self):
        """容量控制：超限时先尝试摘要合并，否则淘汰最旧条目。"""

        if len(self.storage) <= self.max_items:
            return
        overflow = len(self.storage) - self.max_items
        oldest = sorted(self.storage.values(), key=lambda item: item.created_at)
        if self.summarizer is not None and overflow > 0:
            victims, keep = [], []
            for index, item in enumerate(oldest):
                if index < overflow:
                    victims.append(item)
                else:
                    keep.append(item)
            summary_text = self.summarizer([str(item.value) for item in victims])
            self.storage = {item.key: item for item in keep}
            # 直接写入，避免再次触发容量检查造成递归
            summary = MemoryItem(
                key=f"summary:{oldest[0].created_at}",
                value=summary_text,
                memory_type="summary",
                owner=victims[0].owner,
            )
            self.storage[summary.key] = summary
            # 摘要条目也占容量：继续淘汰到上限内（摘要是最新条目，不会被淘汰）
            while len(self.storage) > self.max_items:
                oldest_key = min(self.storage, key=lambda k: self.storage[k].created_at)
                self.storage.pop(oldest_key)
            return
        for item in oldest[:overflow]:
            self.storage.pop(item.key, None)

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        owner: str | None = None,
        top_k: int = 5,
    ):
        """混合检索：仅返回隔离可见且未过期的记忆。"""

        self.purge_expired()
        retriever = HybridRetriever(embedder=self.embedder)
        candidates = [
            (item.key, f"{item.key} {item.tags and ' '.join(item.tags) or ''} {item.value}")
            for item in self.storage.values()
            if self._visible(item, owner)
        ]
        hits = retriever.search(query, candidates, top_k=top_k)
        return [
            {"item": self.storage[hit.key], "score": hit.score}
            for hit in hits
            if hit.score > 0
        ]


__all__ = ["LongTermMemory"]
