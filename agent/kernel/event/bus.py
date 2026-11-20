from collections import defaultdict
from collections.abc import Awaitable, Callable

from agent.kernel.event.events import AgentEvent


EventHandler = Callable[[AgentEvent], Awaitable[None]]


class EventBus:
    """
    简单异步事件总线。

    插件之间通过事件通信，避免强耦合。
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_name]:
            self._handlers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)

    def has_subscribers(self, event_name: str) -> bool:
        """同步上下文（如 Orchestrator）发事件前判断是否有订阅者，避免空转。"""
        return bool(self._handlers.get(event_name))

    async def publish(self, event: AgentEvent) -> None:
        handlers = list(self._handlers.get(event.name, []))

        for handler in handlers:
            await handler(event)