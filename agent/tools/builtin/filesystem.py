"""
SmartOps Builtin Filesystem Tool.

提供受控文件系统能力。

默认原则：

    - 路径必须经过规范化
    - 可限制 allowed_roots
    - 默认以只读为主
    - 防止路径穿越
    - 限制文件大小
    - 不执行文件内容
    - 不调用 shell
    - 写操作必须由上层 Permission / Risk / Approval 控制

建议生产环境进一步与：

    FilesystemSandbox

绑定。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


class FilesystemToolError(RuntimeError):
    """Filesystem Tool 基础异常。"""


class FilesystemAccessDenied(FilesystemToolError):
    """文件访问被拒绝。"""


class FilesystemTooLarge(FilesystemToolError):
    """文件超过读取限制。"""


class FilesystemTool:
    """
    受控文件系统 Tool。
    """

    def __init__(
        self,
        *,
        allowed_roots: list[str | Path] | None = None,
        max_read_bytes: int = 2_000_000,
        allow_write: bool = False,
    ) -> None:
        self.allowed_roots = [
            Path(root).resolve()
            for root in (
                allowed_roots or []
            )
        ]

        self.max_read_bytes = max_read_bytes
        self.allow_write = allow_write

    # ---------------------------------------------------------
    # Read
    # ---------------------------------------------------------

    async def read_text(
        self,
        path: str | Path,
        *,
        encoding: str = "utf-8",
    ) -> str:
        """
        读取文本文件。
        """
        target = self._resolve(path)

        self._check_file_size(
            target
        )

        return await asyncio.to_thread(
            target.read_text,
            encoding=encoding,
        )

    async def exists(
        self,
        path: str | Path,
    ) -> bool:
        """
        判断路径是否存在。
        """
        target = self._resolve(path)

        return await asyncio.to_thread(
            target.exists
        )

    async def list_dir(
        self,
        path: str | Path,
    ) -> list[str]:
        """
        列出目录。
        """
        target = self._resolve(path)

        if not target.exists():
            raise FilesystemToolError(
                f"目录不存在：{target}"
            )

        if not target.is_dir():
            raise FilesystemToolError(
                f"不是目录：{target}"
            )

        entries = await asyncio.to_thread(
            lambda: list(target.iterdir())
        )

        return sorted(
            [
                entry.name
                for entry in entries
            ]
        )

    async def stat(
        self,
        path: str | Path,
    ) -> dict[str, Any]:
        """
        获取文件 / 目录基本信息。
        """
        target = self._resolve(path)

        stat_result = await asyncio.to_thread(
            target.stat
        )

        return {
            "path": str(target),
            "exists": True,
            "is_file": target.is_file(),
            "is_dir": target.is_dir(),
            "size": stat_result.st_size,
            "modified_time": stat_result.st_mtime,
        }

    # ---------------------------------------------------------
    # Write
    # ---------------------------------------------------------

    async def write_text(
        self,
        path: str | Path,
        content: str,
        *,
        encoding: str = "utf-8",
    ) -> None:
        """
        写入文本。

        默认关闭。

        生产环境建议：
            Permission
            Risk
            Approval
            FilesystemSandbox
        全部通过后再调用。
        """
        if not self.allow_write:
            raise FilesystemAccessDenied(
                "Filesystem Tool 当前未开启写权限"
            )

        target = self._resolve(path)

        await asyncio.to_thread(
            target.write_text,
            content,
            encoding=encoding,
        )

    # ---------------------------------------------------------
    # Security
    # ---------------------------------------------------------

    def _resolve(
        self,
        path: str | Path,
    ) -> Path:
        """
        规范化路径并检查 allowed_roots。
        """
        raw = Path(path)

        try:
            target = raw.resolve()
        except OSError as exc:
            raise FilesystemAccessDenied(
                f"无法解析路径：{path}"
            ) from exc

        if not self.allowed_roots:
            # 没有根目录时仍允许受控使用，
            # 但生产环境建议始终指定 allowed_roots。
            return target

        for root in self.allowed_roots:
            try:
                target.relative_to(root)
                return target
            except ValueError:
                continue

        raise FilesystemAccessDenied(
            f"路径不在允许目录内：{target}"
        )

    def _check_file_size(
        self,
        path: Path,
    ) -> None:
        if not path.exists():
            raise FilesystemToolError(
                f"文件不存在：{path}"
            )

        if not path.is_file():
            raise FilesystemToolError(
                f"不是文件：{path}"
            )

        size = path.stat().st_size

        if size > self.max_read_bytes:
            raise FilesystemTooLarge(
                (
                    f"文件过大：{size} bytes，"
                    f"限制为 {self.max_read_bytes} bytes"
                )
            )


__all__ = [
    "FilesystemTool",
    "FilesystemToolError",
    "FilesystemAccessDenied",
    "FilesystemTooLarge",
]