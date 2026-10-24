from agent.sdk.risk import RiskManifest


class RiskRegistry:

    def __init__(self) -> None:
        self._manifests: dict[
            str,
            RiskManifest,
        ] = {}

    def register(
        self,
        manifest: RiskManifest,
    ) -> None:
        self._manifests[
            manifest.plugin_id
        ] = manifest

    def unregister(
        self,
        plugin_id: str,
    ) -> None:
        self._manifests.pop(
            plugin_id,
            None,
        )

    def get(
        self,
        plugin_id: str,
    ) -> RiskManifest | None:
        return self._manifests.get(
            plugin_id
        )