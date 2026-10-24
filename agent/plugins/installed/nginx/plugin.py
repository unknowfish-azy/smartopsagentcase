from pathlib import Path

from agent.sdk.manifest import PluginManifest
from agent.sdk.plugin import Plugin

from .tools import (
    NginxConfigTestTool,
    NginxLogsTool,
    NginxStatusTool,
)


class NginxPlugin(Plugin):

    def __init__(self) -> None:

        manifest = PluginManifest.from_yaml(
            Path(__file__).parent
            / "manifest.yaml"
        )

        super().__init__(manifest)

        self.tools = [
            NginxStatusTool(),
            NginxConfigTestTool(),
            NginxLogsTool(),
        ]

    async def mount(self, runtime) -> None:

        runtime.plugins.register(self)

        for permission in self.manifest.permissions:
            runtime.permissions.register(
                permission
            )

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