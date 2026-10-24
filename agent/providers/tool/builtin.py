from agent.registry.tool_registry import ToolRegistry


class BuiltinToolProvider:

    def __init__(
        self,
        registry: ToolRegistry,
    ) -> None:
        self.registry = registry

    def register(
        self,
        tool,
    ) -> None:
        self.registry.register(tool)