"""
SmartOps Python Tool Adapter.

用于把受控 Python Callable 适配成统一 Tool。

重要原则：

    Tool 可以调用已经注册的 Python Callable。

    Tool 不接受任意字符串 Python 代码执行。

因此本文件明确禁止：
    eval()
    exec()
    动态 import 用户输入代码

真正的 Python 扩展能力应该通过：
    Plugin
    Tool Registry
    Provider
    已注册 Callable
完成。
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Callable


class PythonToolError(RuntimeError):
    """Python Tool 基础异常。"""


class PythonToolNotAllowed(PythonToolError):
    """Python Callable 未被允许。"""


@dataclass(slots=True)
class PythonToolResult:
    """
    Python Tool 执行结果。
    """

    tool_name: str
    result: Any
    elapsed_ms: int
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "result": self.result,
            "elapsed_ms": self.elapsed_ms,
            "success": self.success,
            "error": self.error,
        }


class PythonToolAdapter:
    """
    受控 Python Callable Adapter。
    """

    def __init__(
        self,
        *,
        allowed_tools: dict[str, Callable[..., Any]] | None = None,
        default_timeout: float = 30.0,
    ) -> None:
        self.allowed_tools = dict(
            allowed_tools or {}
        )

        self.default_timeout = default_timeout

    def register(
        self,
        name: str,
        callable_obj: Callable[..., Any],
    ) -> None:
        """
        注册一个已知 Python Callable。
        """
        if not name.strip():
            raise ValueError(
                "Tool name 不能为空"
            )

        if not callable(callable_obj):
            raise TypeError(
                "callable_obj 必须是 Callable"
            )

        self.allowed_tools[name] = callable_obj

    def unregister(
        self,
        name: str,
    ) -> bool:
        """
        删除 Tool。
        """
        return (
            self.allowed_tools.pop(
                name,
                None,
            )
            is not None
        )

    def exists(
        self,
        name: str,
    ) -> bool:
        return name in self.allowed_tools

    async def execute(
        self,
        name: str,
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> PythonToolResult:
        """
        执行已注册 Callable。
        """
        callable_obj = self.allowed_tools.get(
            name
        )

        if callable_obj is None:
            raise PythonToolNotAllowed(
                f"Python Tool 未注册：{name}"
            )

        effective_timeout = (
            timeout
            if timeout is not None
            else self.default_timeout
        )

        if effective_timeout <= 0:
            raise ValueError(
                "timeout 必须大于 0"
            )

        start = time.monotonic()

        try:
            if inspect.iscoroutinefunction(
                callable_obj
            ):
                result = await asyncio.wait_for(
                    callable_obj(
                        *args,
                        **kwargs,
                    ),
                    timeout=effective_timeout,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        callable_obj,
                        *args,
                        **kwargs,
                    ),
                    timeout=effective_timeout,
                )

            return PythonToolResult(
                tool_name=name,
                result=result,
                elapsed_ms=int(
                    (time.monotonic() - start)
                    * 1000
                ),
            )

        except asyncio.TimeoutError:
            return PythonToolResult(
                tool_name=name,
                result=None,
                elapsed_ms=int(
                    (time.monotonic() - start)
                    * 1000
                ),
                success=False,
                error="python tool timeout",
            )

        except Exception as exc:
            return PythonToolResult(
                tool_name=name,
                result=None,
                elapsed_ms=int(
                    (time.monotonic() - start)
                    * 1000
                ),
                success=False,
                error=str(exc),
            )

    def list_tools(self) -> list[str]:
        """
        返回已注册 Python Tool。
        """
        return sorted(
            self.allowed_tools.keys()
        )


__all__ = [
    "PythonToolAdapter",
    "PythonToolResult",
    "PythonToolError",
    "PythonToolNotAllowed",
]