"""
SmartOps Builtin Shell Tool.

受控 Shell / Process Tool。

核心安全原则：

    1. 禁止 shell=True
    2. 使用参数列表执行
    3. 命令 Allowlist
    4. 可限制工作目录
    5. 可限制执行时间
    6. 限制 stdout / stderr 大小
    7. 禁止显式危险命令
    8. Tool 本身不代替 SafeAgent
    9. 生产环境必须结合 ProcessSandbox

允许示例：

    shell.execute(
        ["uname", "-a"]
    )

    shell.execute(
        ["ss", "-lntp"]
    )

禁止：

    shell.execute(
        ["rm", "-rf", "/"]
    )

更不允许：

    shell.execute(
        user_input
    )
    + shell=True
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class ShellToolError(RuntimeError):
    """Shell Tool 基础异常。"""


class ShellCommandDenied(ShellToolError):
    """Shell 命令被拒绝。"""


class ShellCommandTimeout(ShellToolError):
    """Shell 命令超时。"""


@dataclass(slots=True)
class ShellResult:
    """
    Shell 执行结果。
    """

    command: list[str]

    returncode: int

    stdout: str

    stderr: str

    timed_out: bool = False

    truncated: bool = False

    @property
    def success(self) -> bool:
        return (
            self.returncode == 0
            and not self.timed_out
        )

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "success": self.success,
        }


class ShellTool:
    """
    SmartOps 受控 Shell Tool。

    默认只允许常见只读诊断命令。
    """

    DEFAULT_ALLOWED_COMMANDS = {
        # Linux
        "cat",
        "df",
        "du",
        "free",
        "grep",
        "head",
        "hostname",
        "id",
        "ip",
        "ls",
        "netstat",
        "pgrep",
        "ps",
        "pwd",
        "ss",
        "tail",
        "uname",
        "uptime",
        "whoami",

        # Windows
        "systeminfo",
        "tasklist",
        "ipconfig",
    }

    DANGEROUS_COMMANDS = {
        "rm",
        "rmdir",
        "del",
        "format",
        "shutdown",
        "reboot",
        "kill",
        "pkill",
        "killall",
        "iptables",
        "nft",
        "systemctl",
        "service",
        "mount",
        "umount",
        "chmod",
        "chown",
        "useradd",
        "userdel",
        "passwd",
        "dd",
        "mkfs",
        "docker",
        "kubectl",
        "terraform",
    }

    def __init__(
        self,
        *,
        allowed_commands: set[str] | None = None,
        allowed_workdirs: list[str | Path]
        | None = None,
        timeout: int = 20,
        max_output_chars: int = 20_000,
    ) -> None:
        self.allowed_commands = set(
            allowed_commands
            or self.DEFAULT_ALLOWED_COMMANDS
        )

        self.allowed_workdirs = [
            Path(path).resolve()
            for path in (
                allowed_workdirs or []
            )
        ]

        self.timeout = timeout
        self.max_output_chars = (
            max_output_chars
        )

    async def execute(
        self,
        args: Sequence[str],
        *,
        cwd: str | Path | None = None,
        timeout: int | None = None,
    ) -> ShellResult:
        """
        执行受控命令。

        args 必须是参数列表。

        正确：

            ["ss", "-lntp"]

        错误：

            ["ss -lntp"]
        """
        normalized = self._normalize_args(
            args
        )

        command_name = self._command_name(
            normalized[0]
        )

        self._check_command_allowed(
            command_name
        )

        self._check_dangerous_arguments(
            normalized
        )

        working_directory = (
            self._resolve_cwd(cwd)
        )

        effective_timeout = (
            timeout
            if timeout is not None
            else self.timeout
        )

        if effective_timeout <= 0:
            raise ValueError(
                "timeout 必须大于 0"
            )

        process = await self._create_process(
            normalized,
            working_directory,
        )

        try:
            stdout, stderr = (
                await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
            )

        except asyncio.TimeoutError:
            process.kill()

            try:
                await process.wait()
            except Exception:
                pass

            raise ShellCommandTimeout(
                (
                    "Shell command timeout: "
                    f"{effective_timeout}s"
                )
            )

        stdout_text = (
            stdout.decode(
                "utf-8",
                errors="replace",
            )
            if isinstance(stdout, bytes)
            else str(stdout or "")
        )

        stderr_text = (
            stderr.decode(
                "utf-8",
                errors="replace",
            )
            if isinstance(stderr, bytes)
            else str(stderr or "")
        )

        truncated = False

        if len(stdout_text) > self.max_output_chars:
            stdout_text = (
                stdout_text[
                    : self.max_output_chars
                ]
                + "\n[SmartOps] stdout truncated."
            )

            truncated = True

        if len(stderr_text) > self.max_output_chars:
            stderr_text = (
                stderr_text[
                    : self.max_output_chars
                ]
                + "\n[SmartOps] stderr truncated."
            )

            truncated = True

        return ShellResult(
            command=list(normalized),
            returncode=(
                process.returncode
                if process.returncode is not None
                else 1
            ),
            stdout=stdout_text,
            stderr=stderr_text,
            timed_out=False,
            truncated=truncated,
        )

    async def _create_process(
        self,
        args: list[str],
        cwd: Path | None,
    ) -> asyncio.subprocess.Process:
        """
        创建子进程。

        明确不使用 shell=True。
        """
        try:
            return await asyncio.create_subprocess_exec(
                *args,
                cwd=(
                    str(cwd)
                    if cwd is not None
                    else None
                ),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        except FileNotFoundError as exc:
            raise ShellToolError(
                f"命令不存在：{args[0]}"
            ) from exc

        except OSError as exc:
            raise ShellToolError(
                f"无法启动命令：{exc}"
            ) from exc

    def _normalize_args(
        self,
        args: Sequence[str],
    ) -> list[str]:
        if not args:
            raise ShellCommandDenied(
                "命令不能为空"
            )

        normalized: list[str] = []

        for arg in args:
            if not isinstance(
                arg,
                str,
            ):
                raise ShellCommandDenied(
                    "所有参数必须是字符串"
                )

            if not arg:
                raise ShellCommandDenied(
                    "命令参数不能为空字符串"
                )

            normalized.append(arg)

        return normalized

    def _command_name(
        self,
        raw_name: str,
    ) -> str:
        """
        提取实际命令名。

        Windows：
            C:\\Windows\\System32\\tasklist.exe

        Linux：
            /usr/bin/ss
        """
        name = Path(
            raw_name
        ).name.lower()

        if name.endswith(".exe"):
            name = name[:-4]

        return name

    def _check_command_allowed(
        self,
        command_name: str,
    ) -> None:
        if command_name in (
            self.DANGEROUS_COMMANDS
        ):
            raise ShellCommandDenied(
                (
                    "危险命令被 Shell Tool "
                    f"禁止：{command_name}"
                )
            )

        if command_name not in (
            {
                item.lower()
                for item
                in self.allowed_commands
            }
        ):
            raise ShellCommandDenied(
                (
                    "命令未加入 Allowlist："
                    f"{command_name}"
                )
            )

    def _check_dangerous_arguments(
        self,
        args: Sequence[str],
    ) -> None:
        """
        检查明显危险参数。

        这里只做第一层保护。
        最终仍应由 ProcessSandbox 决定。
        """
        forbidden_fragments = {
            "|",
            "&&",
            "||",
            ";",
            ">",
            ">>",
            "<",
            "`",
            "$(",
            "${",
        }

        for arg in args:
            for fragment in forbidden_fragments:
                if fragment in arg:
                    raise ShellCommandDenied(
                        (
                            "检测到 Shell 元字符："
                            f"{fragment}"
                        )
                    )

        dangerous_flags = {
            "--force",
            "--delete",
            "--privileged",
            "--device",
            "--cap-add",
            "--pid=host",
            "--network=host",
        }

        for arg in args:
            if arg.lower() in dangerous_flags:
                raise ShellCommandDenied(
                    f"危险参数被禁止：{arg}"
                )

    def _resolve_cwd(
        self,
        cwd: str | Path | None,
    ) -> Path | None:
        if cwd is None:
            return None

        target = Path(cwd).resolve()

        if not self.allowed_workdirs:
            return target

        for root in self.allowed_workdirs:
            try:
                target.relative_to(root)
                return target
            except ValueError:
                continue

        raise ShellCommandDenied(
            (
                "工作目录不在允许范围："
                f"{target}"
            )
        )

    def describe(self) -> dict:
        """
        返回当前 Shell Tool 能力描述。
        """
        return {
            "type": "shell",
            "allowed_commands": sorted(
                self.allowed_commands
            ),
            "dangerous_commands": sorted(
                self.DANGEROUS_COMMANDS
            ),
            "timeout": self.timeout,
            "max_output_chars": (
                self.max_output_chars
            ),
            "shell": False,
        }


__all__ = [
    "ShellTool",
    "ShellResult",
    "ShellToolError",
    "ShellCommandDenied",
    "ShellCommandTimeout",
]
