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
    ):

        item = MemoryItem(
            key=key,
            value=value,
            memory_type=memory_type,
        )

        if memory_type == "long_term":
            self.long_term.save(item)
        else:
            self.short_term.add(item)

        return item

    def recall(
        self,
        key: str,
    ):

        item = self.long_term.get(key)

        if item:
            return item

        for item in reversed(
            self.short_term.get_all()
        ):
            if item.key == key:
                return item

        return None