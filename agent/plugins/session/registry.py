from __future__ import annotations

from agent.plugins.session.provider import (
    SessionProvider,
)


class SessionProviderRegistry:

    def __init__(self) -> None:

        self._providers: dict[
            str,
            SessionProvider,
        ] = {}

    def register(
        self,
        name: str,
        provider: SessionProvider,
    ) -> None:

        self._providers[
            name
        ] = provider

    def unregister(
        self,
        name: str,
    ) -> None:

        self._providers.pop(
            name,
            None,
        )

    def get(
        self,
        name: str,
    ) -> SessionProvider | None:

        return self._providers.get(
            name
        )

    def list(self) -> list[str]:

        return list(
            self._providers.keys()
        )

    def exists(
        self,
        name: str,
    ) -> bool:

        return name in self._providers