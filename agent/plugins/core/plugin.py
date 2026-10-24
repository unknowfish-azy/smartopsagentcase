from pathlib import Path

from agent.sdk.manifest import PluginManifest
from agent.sdk.plugin import Plugin


class ManifestPlugin(Plugin):

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
    ) -> "ManifestPlugin":

        directory = Path(directory)

        manifest = (
            PluginManifest.from_yaml(
                directory / "manifest.yaml"
            )
        )

        plugin = cls(manifest)

        return plugin

    async def mount(self, runtime) -> None:

        runtime.plugins.register(self)

        for permission in (
            self.manifest.permissions
        ):
            runtime.permissions.register(
                permission
            )

        if self.manifest.risk_manifest:
            runtime.risks.register(
                self.manifest.risk_manifest
            )

    async def unmount(self, runtime) -> None:

        runtime.plugins.unregister(
            self.id
        )