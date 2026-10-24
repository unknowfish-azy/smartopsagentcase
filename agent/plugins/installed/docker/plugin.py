from pathlib import Path

from agent.sdk.manifest import PluginManifest
from agent.sdk.plugin import Plugin

from .tools import (
    DockerComposeTool,
    DockerInspectTool,
    DockerLogsTool,
    DockerPsTool,
    DockerRestartTool,
)


class DockerPlugin(Plugin):
    """
    SmartOps Docker Plugin.

    提供受控Docker运维能力。
    """

    def __init__(self) -> None:
        manifest_path = (
            Path(__file__).parent / "manifest.yaml"
        )

        manifest = PluginManifest.from_yaml(
            manifest_path
        )

        super().__init__(manifest)

        self.tools = [
            DockerPsTool(),
            DockerInspectTool(),
            DockerLogsTool(),
            DockerComposeTool(),
            DockerRestartTool(),
        ]

    async def mount(self, runtime) -> None:
        runtime.plugins.register(self)

        for permission in self.manifest.permissions:
            runtime.permissions.register(permission)

        if self.manifest.risk_manifest:
            runtime.risks.register(
                self.manifest.risk_manifest
            )

        for tool in self.tools:
            runtime.tools.register(tool)

    async def unmount(self, runtime) -> None:
        for tool in self.tools:
            runtime.tools.unregister(
                tool.definition.name
            )

        runtime.plugins.unregister(self.id)