from pathlib import Path

from agent.sdk.manifest import PluginManifest
from agent.sdk.plugin import Plugin


class ServerPlugin(Plugin):

    def __init__(self) -> None:

        manifest_path = (
            Path(__file__).parent
            / "manifest.yaml"
        )

        manifest = (
            PluginManifest.from_yaml(
                manifest_path
            )
        )

        super().__init__(manifest)

    async def mount(self, runtime) -> None:

        for permission in self.manifest.permissions:
            runtime.permissions.register(
                permission
            )

        if self.manifest.risk_manifest:
            runtime.risks.register(
                self.manifest.risk_manifest
            )

        runtime.plugins.register(self)

    async def unmount(self, runtime) -> None:

        runtime.plugins.unregister(
            self.id
        )