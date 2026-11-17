from collections import deque

from .models import MemoryItem


class ShortTermMemory:

    def __init__(
        self,
        max_items: int = 50,
    ):
        self.items = deque(
            maxlen=max_items
        )

    def add(
        self,
        item: MemoryItem,
    ):
        self.items.append(item)

    def get_all(self):
        return list(self.items)

    def clear(self):
        self.items.clear()

    def compress(self, summarizer, keep_recent: int = 10) -> str | None:
        """窗口溢出前的滚动压缩：把较早的记忆摘要成一条，保留最近 keep_recent 条。

        返回摘要文本；没有可压缩内容时返回 None。
        """

        items = list(self.items)
        if len(items) <= keep_recent:
            return None

        victims, keep = items[:-keep_recent], items[-keep_recent:]
        summary_text = summarizer([str(item.value) for item in victims])
        summary = MemoryItem(
            key=f"session-summary:{victims[-1].created_at}",
            value=summary_text,
            memory_type="summary",
            owner=victims[0].owner,
        )
        self.items.clear()
        self.items.append(summary)
        for item in keep:
            self.items.append(item)
        return summary_text