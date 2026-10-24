from agent.sdk.tool import PluginTool


class ToolRegistry:

    def __init__(self) -> None:
        self._tools: dict[str, PluginTool] = {}

    def register(
        self,
        tool: PluginTool,
    ) -> None:
        self._tools[
            tool.definition.name
        ] = tool

    def unregister(
        self,
        name: str,
    ) -> None:
        self._tools.pop(name, None)

    def get(
        self,
        name: str,
    ) -> PluginTool | None:
        return self._tools.get(name)

    def list(self) -> list[PluginTool]:
        return list(self._tools.values())