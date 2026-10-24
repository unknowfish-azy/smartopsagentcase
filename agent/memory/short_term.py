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