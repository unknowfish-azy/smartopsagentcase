from .models import MemoryItem


class LongTermMemory:
    """
    当前使用内存实现。

    后续可以替换成：
    Redis / MySQL / Vector DB。
    """

    def __init__(self):
        self.storage: dict[
            str,
            MemoryItem,
        ] = {}

    def save(
        self,
        item: MemoryItem,
    ):
        self.storage[item.key] = item

    def get(
        self,
        key: str,
    ):
        return self.storage.get(key)

    def delete(
        self,
        key: str,
    ):
        self.storage.pop(
            key,
            None,
        )

    def clear(self):
        self.storage.clear()