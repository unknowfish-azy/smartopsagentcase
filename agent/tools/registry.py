from .base import AgentTool


class ToolRegistry:

    def __init__(self):
        self._tools: dict[
            str,
            AgentTool,
        ] = {}

    def register(
        self,
        tool: AgentTool,
    ):
        if not tool.name:
            raise ValueError(
                "工具必须定义 name"
            )

        if tool.name in self._tools:
            raise ValueError(
                f"工具已存在: {tool.name}"
            )

        self._tools[tool.name] = tool

    def get(
        self,
        name: str,
    ):
        return self._tools.get(name)

    def list_tools(self):
        return list(
            self._tools.values()
        )

    def remove(
        self,
        name: str,
    ):
        self._tools.pop(
            name,
            None,
        )