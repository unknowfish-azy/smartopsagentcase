class ProviderRegistry:

    def __init__(self) -> None:
        self._providers = {}

    def register(
        self,
        provider,
    ) -> None:
        self._providers[
            provider.name
        ] = provider

    def unregister(
        self,
        name: str,
    ) -> None:
        self._providers.pop(name, None)

    def get(self, name: str):
        return self._providers.get(name)

    def list(self):
        return list(self._providers.values())