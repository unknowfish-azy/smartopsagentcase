"""
SmartOps Docker Sandbox.

提供 Docker CLI 的受控执行能力。

设计原则：
1. 默认拒绝危险操作
2. 不使用 shell=True
3. 只允许显式声明的 Docker 子命令
4. 限制容器名 / ID 参数
5. 限制命令长度
6. 限制执行超时
7. 返回结构化结果
8. Docker Sandbox 只负责“执行边界”
9. Permission / Risk / SafeAgent 决定“是否允许执行”

典型调用链：

    SafeAgent
        ↓
    Permission
        ↓
    Risk
        ↓
    Approval
        ↓
    DockerSandbox
        ↓
    docker CLI
        ↓
    Verification
        ↓
    Audit
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Sequence

from .base import Sandbox
from .policy import SandboxPolicy


class DockerSandboxError(RuntimeError):
    """Docker Sandbox 基础异常。"""


class DockerCommandDenied(DockerSandboxError):
    """Docker 命令被 Sandbox 拒绝。"""


class DockerCommandTimeout(DockerSandboxError):
    """Docker 命令执行超时。"""


@dataclass(slots=True)
class DockerResult:
    """
    Docker 命令执行结果。
    """

    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def success(self) -> bool:
        """命令是否执行成功。"""
        return self.returncode == 0 and not self.timed_out

    def to_dict(self) -> dict:
        """转换为普通字典，便于日志 / Audit 使用。"""
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "success": self.success,
        }


class DockerSandbox(Sandbox):
    """
    Docker CLI Sandbox。

    默认仅允许：

    - docker ps
    - docker inspect
    - docker logs
    - docker version
    - docker info

    默认不允许：

    - docker rm
    - docker rmi
    - docker kill
    - docker stop
    - docker start
    - docker restart
    - docker exec
    - docker run
    - docker compose
    - docker system prune

    高风险写操作必须由上层 SafeAgent / Approval 决定，
    不应该绕过 Sandbox 直接执行。
    """

    DEFAULT_ALLOWED_COMMANDS = {
        "ps",
        "inspect",
        "logs",
        "version",
        "info",
    }

    # Docker 容器名称 / ID 的安全字符范围。
    # 允许：
    #   nginx
    #   redis-server
    #   smartops_redis_1
    #   a1b2c3d4...
    SAFE_TARGET_PATTERN = re.compile(
        r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$"
    )

    def __init__(
        self,
        policy: SandboxPolicy | None = None,
        docker_binary: str = "docker",
        timeout: int = 30,
        max_command_length: int = 2000,
        allowed_commands: set[str] | None = None,
    ) -> None:
        """
        初始化 Docker Sandbox。

        Args:
            policy:
                Sandbox 总体策略。
            docker_binary:
                Docker CLI 路径，默认使用 PATH 中的 docker。
            timeout:
                默认命令超时时间，单位秒。
            max_command_length:
                最大命令长度。
            allowed_commands:
                Docker Sandbox 允许的一级子命令。
        """
        super().__init__(policy or SandboxPolicy())

        if timeout <= 0:
            raise ValueError("timeout 必须大于 0")

        if max_command_length <= 0:
            raise ValueError("max_command_length 必须大于 0")

        self.docker_binary = docker_binary
        self.timeout = timeout
        self.max_command_length = max_command_length

        self.allowed_commands = set(
            allowed_commands or self.DEFAULT_ALLOWED_COMMANDS
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        args: Sequence[str],
        *,
        timeout: int | None = None,
    ) -> DockerResult:
        """
        执行 Docker CLI。

        示例：

            result = await sandbox.execute(
                ["ps", "--format", "{{.Names}}"]
            )

        注意：

        args 不应该包含 docker 本身。

        正确：

            ["ps"]

        错误：

            ["docker", "ps"]
        """
        normalized = self._normalize_args(args)

        command_name = normalized[0]

        self._check_command_allowed(command_name)
        self._check_command_arguments(normalized)
        self._check_command_length(normalized)

        effective_timeout = timeout or self.timeout

        if effective_timeout <= 0:
            raise ValueError("timeout 必须大于 0")

        command = [self.docker_binary, *normalized]

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise DockerSandboxError(
                f"找不到 Docker CLI: {self.docker_binary}"
            ) from exc
        except OSError as exc:
            raise DockerSandboxError(
                f"无法启动 Docker CLI: {exc}"
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            process.kill()

            try:
                await process.wait()
            except Exception:
                pass

            raise DockerCommandTimeout(
                f"Docker 命令执行超时：{effective_timeout}s"
            )

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        return DockerResult(
            command=command,
            returncode=process.returncode or 0,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    async def ps(
        self,
        *,
        all_containers: bool = False,
    ) -> DockerResult:
        """
        查看容器列表。

        相当于：

            docker ps
            docker ps -a
        """
        args = ["ps"]

        if all_containers:
            args.append("-a")

        return await self.execute(args)

    async def inspect(
        self,
        target: str,
    ) -> DockerResult:
        """
        查看容器详细信息。
        """
        self._validate_target(target)

        return await self.execute(
            ["inspect", target]
        )

    async def logs(
        self,
        target: str,
        *,
        tail: int = 100,
    ) -> DockerResult:
        """
        查看容器日志。

        默认只读取最近 100 行，避免一次读取过大日志。
        """
        self._validate_target(target)

        if tail < 1 or tail > 10000:
            raise ValueError("tail 必须在 1 到 10000 之间")

        return await self.execute(
            [
                "logs",
                "--tail",
                str(tail),
                target,
            ]
        )

    async def version(self) -> DockerResult:
        """
        查看 Docker 版本。
        """
        return await self.execute(
            ["version"]
        )

    async def info(self) -> DockerResult:
        """
        查看 Docker Engine 信息。
        """
        return await self.execute(
            ["info"]
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _normalize_args(
        self,
        args: Sequence[str],
    ) -> list[str]:
        """
        标准化参数。

        防止：
        - 空参数
        - 非字符串参数
        - 用户把 docker 本身重复传入
        """
        if not args:
            raise DockerCommandDenied(
                "Docker 命令不能为空"
            )

        normalized = []

        for arg in args:
            if not isinstance(arg, str):
                raise DockerCommandDenied(
                    "Docker 参数必须全部为字符串"
                )

            if not arg:
                raise DockerCommandDenied(
                    "Docker 参数不能为空字符串"
                )

            normalized.append(arg)

        # 防止调用方重复传 docker。
        if normalized[0] in {"docker", "docker.exe"}:
            raise DockerCommandDenied(
                "args 不应该包含 docker / docker.exe"
            )

        return normalized

    def _check_command_allowed(
        self,
        command_name: str,
    ) -> None:
        """
        检查一级 Docker 子命令。
        """
        if command_name not in self.allowed_commands:
            raise DockerCommandDenied(
                f"Docker 子命令未被 Sandbox 允许：{command_name}"
            )

    def _check_command_arguments(
        self,
        args: Sequence[str],
    ) -> None:
        """
        检查危险参数。

        这里采用保守策略：
        只要出现明显可能导致写操作 / 提权 / 注入的参数，
        就直接拒绝。
        """
        dangerous_fragments = {
            "--privileged",
            "--cap-add",
            "--device",
            "--pid=host",
            "--network=host",
            "--ipc=host",
            "--uts=host",
            "--userns=host",
            "/var/run/docker.sock",
            "docker.sock",
        }

        for arg in args:
            lowered = arg.lower()

            for fragment in dangerous_fragments:
                if fragment in lowered:
                    raise DockerCommandDenied(
                        f"检测到受限制的 Docker 参数：{arg}"
                    )

    def _check_command_length(
        self,
        args: Sequence[str],
    ) -> None:
        """
        检查命令总长度。
        """
        command_text = " ".join(args)

        if len(command_text) > self.max_command_length:
            raise DockerCommandDenied(
                "Docker 命令长度超过 Sandbox 限制"
            )

    def _validate_target(
        self,
        target: str,
    ) -> None:
        """
        校验容器名 / 容器 ID。

        不接受：
        - 空值
        - 空格
        - shell 特殊字符
        - 路径
        - 重定向
        - 命令拼接
        """
        if not isinstance(target, str):
            raise DockerCommandDenied(
                "Docker target 必须是字符串"
            )

        if not target:
            raise DockerCommandDenied(
                "Docker target 不能为空"
            )

        if len(target) > 128:
            raise DockerCommandDenied(
                "Docker target 过长"
            )

        if not self.SAFE_TARGET_PATTERN.fullmatch(target):
            raise DockerCommandDenied(
                f"非法 Docker target：{target}"
            )

    # ------------------------------------------------------------------
    # Safety helpers
    # ------------------------------------------------------------------

    def is_read_only_command(
        self,
        args: Sequence[str],
    ) -> bool:
        """
        判断是否属于 Sandbox 当前定义的只读命令。

        该方法只用于辅助 SafeAgent / PolicyEngine，
        不代表可以绕过 Permission / Risk。
        """
        if not args:
            return False

        try:
            normalized = self._normalize_args(args)
        except DockerSandboxError:
            return False

        return normalized[0] in {
            "ps",
            "inspect",
            "logs",
            "version",
            "info",
        }

    def describe(self) -> dict:
        """
        返回 Sandbox 当前策略信息。
        """
        return {
            "type": "docker",
            "docker_binary": self.docker_binary,
            "timeout": self.timeout,
            "max_command_length": self.max_command_length,
            "allowed_commands": sorted(self.allowed_commands),
            "read_only_commands": sorted(
                {
                    "ps",
                    "inspect",
                    "logs",
                    "version",
                    "info",
                }
            ),
        }


__all__ = [
    "DockerSandbox",
    "DockerSandboxError",
    "DockerCommandDenied",
    "DockerCommandTimeout",
    "DockerResult",
]