from pathlib import Path

from agent.sdk.exceptions import SandboxError


class FilesystemSandbox:

    def __init__(
        self,
        allowed_root: str,
    ) -> None:

        self.allowed_root = Path(
            allowed_root
        ).resolve()

    def validate_path(
        self,
        path: str,
    ) -> Path:

        target = Path(path).resolve()

        try:
            target.relative_to(
                self.allowed_root
            )
        except ValueError as exc:
            raise SandboxError(
                f"Path outside sandbox: {target}"
            ) from exc

        return target

    def read_text(
        self,
        path: str,
    ) -> str:

        target = self.validate_path(path)

        return target.read_text(
            encoding="utf-8"
        )