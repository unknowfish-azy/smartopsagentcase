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

    def register_desktop_tools(
        self,
        hand,
        *,
        enabled: bool | None = None,
    ):
        """注册 desktop.* 六个工具。

        `hand` 是 `agent.tools.desktop.DesktopHand`（driver + gateway 的组合）。
        输入组默认关闭由 gateway 策略决定，注册本身不代表可点击 / 可输入。
        故意不注册 `desktop.resume`：急停恢复只能由人做（ARCHITECTURE §9）。

        `enabled=None` 时读环境变量 `DESKTOP_HAND_ENABLED`（默认 false）；
        false 时仍注册但把所有 desktop.* 工具的 definition.implementation_status 设为
        UNAVAILABLE，planner 的 catalog 会标注 "(不可用)" 让 LLM 一眼看见。
        """
        from ..desktop.policy import desktop_hand_enabled
        from .desktop import build_desktop_tools

        if enabled is None:
            enabled = desktop_hand_enabled()

        for tool in build_desktop_tools(hand, enabled=enabled):
            self.register(tool)