"""工具层错误分类（P0 执行闭环加固）。

Agent 必须能区分不同失败类别并采取不同策略：
* PARAMETER / PERMISSION：致命，重试无意义，直接终止并上报；
* NETWORK / TIMEOUT：可重试（且仅限幂等工具），走指数退避；
* RESOURCE_NOT_FOUND / BUSINESS：可恢复，上报后可换方案（由上层重规划）；
* UNKNOWN：默认不可重试，保守处理。
"""

from __future__ import annotations

from enum import Enum


class ToolErrorCategory(str, Enum):

    PARAMETER = "PARAMETER"
    PERMISSION = "PERMISSION"
    NETWORK = "NETWORK"
    TIMEOUT = "TIMEOUT"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    BUSINESS = "BUSINESS"
    UNKNOWN = "UNKNOWN"


# 失败分级：轻微（重试）/ 中等（换方案）/ 严重（终止上报）
FAILURE_GRADE: dict[ToolErrorCategory, str] = {
    ToolErrorCategory.NETWORK: "retryable",
    ToolErrorCategory.TIMEOUT: "retryable",
    ToolErrorCategory.BUSINESS: "recoverable",
    ToolErrorCategory.RESOURCE_NOT_FOUND: "recoverable",
    ToolErrorCategory.PARAMETER: "fatal",
    ToolErrorCategory.PERMISSION: "fatal",
    ToolErrorCategory.UNKNOWN: "fatal",
}


class ToolExecutionError(Exception):
    """带错误分类的工具执行异常。

    工具实现可以直接抛出该异常精确声明类别；
    未分类异常由 `classify_exception` 兜底归类。
    """

    def __init__(
        self,
        category: ToolErrorCategory | str,
        message: str,
        *,
        retryable: bool | None = None,
    ) -> None:
        self.category = ToolErrorCategory(category)
        self.retryable = (
            FAILURE_GRADE[self.category] == "retryable"
            if retryable is None
            else retryable
        )
        super().__init__(message)


def classify_exception(exc: BaseException) -> ToolExecutionError:
    """把任意异常归类为 ToolExecutionError（幂等，已分类的异常原样返回）。"""

    if isinstance(exc, ToolExecutionError):
        return exc

    if isinstance(exc, PermissionError):
        return ToolExecutionError(ToolErrorCategory.PERMISSION, str(exc))

    if isinstance(exc, LookupError):
        return ToolExecutionError(ToolErrorCategory.RESOURCE_NOT_FOUND, str(exc))

    if isinstance(exc, ValueError):
        return ToolExecutionError(ToolErrorCategory.PARAMETER, str(exc))

    # httpx / 网络 / 超时类：按模块名判断，避免硬依赖 httpx 类型
    module = type(exc).__module__ or ""
    name = type(exc).__name__
    if "timeout" in name.lower():
        return ToolExecutionError(ToolErrorCategory.TIMEOUT, str(exc))
    if "httpx" in module or "connect" in name.lower() or "network" in name.lower():
        return ToolExecutionError(ToolErrorCategory.NETWORK, str(exc))

    return ToolExecutionError(ToolErrorCategory.UNKNOWN, str(exc))


__all__ = [
    "ToolErrorCategory",
    "FAILURE_GRADE",
    "ToolExecutionError",
    "classify_exception",
]
