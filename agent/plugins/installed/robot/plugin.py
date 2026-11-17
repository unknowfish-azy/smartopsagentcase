from pathlib import Path
from typing import TYPE_CHECKING

from agent.sdk.manifest import PluginManifest
from agent.sdk.plugin import Plugin

from .tools import (
    RobotFleetStatusTool,
    RobotFleetSubmitTool,
    RobotReplanRouteTool,
    RobotRouteGenerateTool,
    RobotTaskStatusTool,
    RobotTaskSubmitTool,
    RobotVoiceCommandTool,
)

if TYPE_CHECKING:
    from agent.security_baseline.robot_guard import RobotActionGuard


class RobotPlugin(Plugin):

    def __init__(self, guard: "RobotActionGuard | None" = None) -> None:
        manifest = PluginManifest.from_yaml(
            Path(__file__).parent / "manifest.yaml"
        )
        super().__init__(manifest)
        self.guard = guard

        self.tools = [
            RobotRouteGenerateTool(),
            RobotTaskSubmitTool(),
            RobotTaskStatusTool(),
            RobotVoiceCommandTool(guard=guard),
            RobotFleetSubmitTool(),
            RobotFleetStatusTool(),
            RobotReplanRouteTool(),
        ]

    async def mount(self, runtime) -> None:
        runtime.plugins.register(self)
        for permission in self.manifest.permissions:
            runtime.permissions.register(permission)
        if self.manifest.risk_manifest:
            runtime.risks.register(self.manifest.risk_manifest)
        for tool in self.tools:
            runtime.tools.register(tool)

    async def unmount(self, runtime) -> None:
        for tool in self.tools:
            runtime.tools.unregister(tool.definition.name)
        runtime.plugins.unregister(self.id)
