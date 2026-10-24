from agent.sdk.exceptions import SandboxError


class NetworkSandbox:

    def __init__(
        self,
        allow_network: bool = False,
        allowed_hosts: set[str] | None = None,
    ) -> None:

        self.allow_network = allow_network

        self.allowed_hosts = (
            allowed_hosts or set()
        )

    def validate_host(
        self,
        host: str,
    ) -> None:

        if not self.allow_network:
            raise SandboxError(
                "Network access disabled"
            )

        if (
            self.allowed_hosts
            and host not in self.allowed_hosts
        ):
            raise SandboxError(
                f"Network host not allowed: {host}"
            )