from typing import Any


class KernelRegistry:
    """
    Kernel级别总注册中心。

    不负责具体业务类型。
    """

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def register(
        self,
        category: str,
        name: str,
        value: Any,
    ) -> None:
        self._items.setdefault(category, {})
        self._items[category][name] = value

    def unregister(
        self,
        category: str,
        name: str,
    ) -> None:
        if category in self._items:
            self._items[category].pop(name, None)

    def get(
        self,
        category: str,
        name: str,
    ) -> Any | None:
        return self._items.get(category, {}).get(name)

    def list_category(self, category: str) -> list[Any]:
        return list(self._items.get(category, {}).values())