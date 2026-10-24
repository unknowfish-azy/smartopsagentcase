"""
SmartOps HTTP Tool Adapter.

负责把 HTTP / HTTPS 请求封装成统一 Tool 能力。

设计原则：
    - 默认只允许 HTTP / HTTPS
    - 默认禁止重定向
    - 支持超时
    - 限制响应大小
    - 不执行任意代码
    - 不处理敏感认证信息
    - 不绕过 Permission / Risk / SafeAgent

适合：
    - Health Check
    - Web API
    - Internal Service Check
    - HTTP Evidence Collection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx


class HTTPToolError(RuntimeError):
    """HTTP Tool 基础异常。"""


class HTTPURLDenied(HTTPToolError):
    """URL 被安全策略拒绝。"""


@dataclass(slots=True)
class HTTPRequest:
    """
    HTTP 请求定义。
    """

    method: str
    url: str

    headers: dict[str, str] = field(default_factory=dict)

    params: dict[str, str] = field(default_factory=dict)

    json: Any | None = None

    data: Any | None = None

    timeout: float = 10.0

    follow_redirects: bool = False


@dataclass(slots=True)
class HTTPResponse:
    """
    HTTP 响应。
    """

    status_code: int

    headers: dict[str, str]

    body: str

    url: str

    elapsed_ms: int

    truncated: bool = False

    @property
    def success(self) -> bool:
        return 200 <= self.status_code < 400

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "headers": self.headers,
            "body": self.body,
            "url": self.url,
            "elapsed_ms": self.elapsed_ms,
            "truncated": self.truncated,
            "success": self.success,
        }


class HTTPToolAdapter:
    """
    HTTP Tool Adapter。

    该 Adapter 不决定：
        是否允许访问
        是否属于高风险
        是否需要 Approval

    这些由上层安全架构负责。
    """

    ALLOWED_SCHEMES = {
        "http",
        "https",
    }

    SAFE_METHODS = {
        "GET",
        "HEAD",
        "OPTIONS",
    }

    WRITE_METHODS = {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        max_response_bytes: int = 1_000_000,
        allowed_hosts: set[str] | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self.allowed_hosts = (
            set(allowed_hosts)
            if allowed_hosts is not None
            else None
        )

    async def request(
        self,
        request: HTTPRequest,
    ) -> HTTPResponse:
        """
        执行 HTTP 请求。
        """
        self._validate_request(request)

        timeout = (
            request.timeout
            if request.timeout > 0
            else self.timeout
        )

        start = httpx.Timeout(timeout)

        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=start,
        ) as client:
            response = await client.request(
                method=request.method.upper(),
                url=request.url,
                headers=request.headers,
                params=request.params,
                json=request.json,
                content=request.data,
            )

        raw = response.content

        truncated = False

        if len(raw) > self.max_response_bytes:
            raw = raw[: self.max_response_bytes]
            truncated = True

        body = raw.decode(
            response.encoding
            or "utf-8",
            errors="replace",
        )

        return HTTPResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=body,
            url=str(response.url),
            elapsed_ms=0,
            truncated=truncated,
        )

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> HTTPResponse:
        """
        GET 请求。
        """
        return await self.request(
            HTTPRequest(
                method="GET",
                url=url,
                headers=dict(headers or {}),
                params=dict(params or {}),
                timeout=timeout or self.timeout,
            )
        )

    async def head(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> HTTPResponse:
        """
        HEAD 请求。
        """
        return await self.request(
            HTTPRequest(
                method="HEAD",
                url=url,
                headers=dict(headers or {}),
                timeout=timeout or self.timeout,
            )
        )

    def _validate_request(
        self,
        request: HTTPRequest,
    ) -> None:
        method = request.method.upper()

        if not method:
            raise HTTPToolError(
                "HTTP method 不能为空"
            )

        parsed = urlparse(request.url)

        if parsed.scheme not in self.ALLOWED_SCHEMES:
            raise HTTPURLDenied(
                f"不允许的 URL scheme：{parsed.scheme}"
            )

        if not parsed.hostname:
            raise HTTPURLDenied(
                "URL 缺少 hostname"
            )

        if self.allowed_hosts is not None:
            hostname = parsed.hostname.lower()

            if hostname not in self.allowed_hosts:
                raise HTTPURLDenied(
                    f"hostname 未在允许列表中：{hostname}"
                )

        if request.timeout <= 0:
            raise HTTPToolError(
                "timeout 必须大于 0"
            )

        if self.max_response_bytes <= 0:
            raise HTTPToolError(
                "max_response_bytes 必须大于 0"
            )


__all__ = [
    "HTTPToolAdapter",
    "HTTPRequest",
    "HTTPResponse",
    "HTTPToolError",
    "HTTPURLDenied",
]