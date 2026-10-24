import asyncio

from agent.sdk.exceptions import SandboxError
from agent.sandbox.policy import SandboxPolicy


class ProcessSandbox:

    def __init__(
        self,
        policy: SandboxPolicy,
    ) -> None:
        self.policy = policy

    async def execute(
        self,
        command: str,
        *args: str,
    ) -> str:

        if not self.policy.allow_process:
            raise SandboxError(
                "Process execution disabled"
            )

        if not self.policy.command_allowed(
            command
        ):
            raise SandboxError(
                f"Command not allowed: {command}"
            )

        process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise SandboxError(
                stderr.decode(
                    errors="replace"
                )
            )

        return stdout.decode(
            errors="replace"
        )