"""Legacy-compatible, allowlisted read-only process tool."""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Any


class ShellTool:
    name = "shell.execute"
    description = "执行受控只读诊断命令"
    risk_level = "HIGH"
    requires_approval = True

    ALLOWED_COMMANDS = {"whoami", "hostname", "uptime", "date"}
    FORBIDDEN_FRAGMENTS = (
        "&&", "||", ";", "|", ">", "<", "`", "$(", "${", "\n", "\r",
    )
    DEFAULT_TIMEOUT = 10
    DEFAULT_MAX_OUTPUT_CHARS = 20_000

    def __init__(
        self,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout 必须大于 0")
        if max_output_chars <= 0:
            raise ValueError("max_output_chars 必须大于 0")
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    def execute(self, command: str) -> dict[str, Any]:
        argv = self._tokenize(command)
        command_name = self._command_name(argv[0])

        if command_name not in self.ALLOWED_COMMANDS:
            raise PermissionError("该命令未进入只读安全白名单")

        try:
            result = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"命令执行超时：{self.timeout}s"
            ) from exc

        stdout, stdout_truncated = self._limit_output(result.stdout)
        stderr, stderr_truncated = self._limit_output(result.stderr)

        return {
            "command": argv,
            "return_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": False,
            "truncated": stdout_truncated or stderr_truncated,
            "success": result.returncode == 0,
        }

    def _tokenize(self, command: str) -> list[str]:
        if not isinstance(command, str) or not command.strip():
            raise PermissionError("命令不能为空")

        for fragment in self.FORBIDDEN_FRAGMENTS:
            if fragment in command:
                raise PermissionError(
                    f"检测到禁止的 Shell 元字符：{fragment!r}"
                )

        try:
            argv = shlex.split(command, posix=os.name != "nt")
        except ValueError as exc:
            raise PermissionError("命令参数格式无效") from exc

        if not argv:
            raise PermissionError("命令不能为空")
        return argv

    @staticmethod
    def _command_name(command: str) -> str:
        name = os.path.basename(command).lower()
        return name[:-4] if name.endswith(".exe") else name

    def _limit_output(self, value: str | None) -> tuple[str, bool]:
        output = value or ""
        if len(output) <= self.max_output_chars:
            return output, False
        return (
            output[: self.max_output_chars]
            + "\n[SmartOps] output truncated.",
            True,
        )


__all__ = ["ShellTool"]
