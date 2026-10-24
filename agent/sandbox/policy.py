from dataclasses import dataclass, field


@dataclass
class SandboxPolicy:
    allowed_commands: set[str] = field(
        default_factory=set
    )

    allowed_paths: list[str] = field(
        default_factory=list
    )

    allow_network: bool = False

    allow_process: bool = False

    def command_allowed(
        self,
        command: str,
    ) -> bool:
        return command in self.allowed_commands