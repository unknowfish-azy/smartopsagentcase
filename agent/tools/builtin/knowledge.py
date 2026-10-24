"""
SmartOps Builtin Knowledge Tool.

负责向 Knowledge Service 请求：

    - Search
    - Hybrid Retrieval
    - Evidence
    - Citation

Knowledge Tool 不直接执行系统操作。

职责：

    User Question
        ↓
    Knowledge Search
        ↓
    Evidence
        ↓
    Agent Reasoning

版本过滤、Reranker、Evidence、Trust
由 Knowledge Service 负责。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


class KnowledgeToolError(RuntimeError):
    """Knowledge Tool 基础异常。"""


@dataclass(slots=True)
class KnowledgeSearchRequest:
    """
    知识检索请求。
    """

    query: str

    top_k: int = 5

    version: str | None = None

    source: str | None = None

    filters: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(slots=True)
class KnowledgeSearchResult:
    """
    知识检索结果。
    """

    query: str

    items: list[dict[str, Any]]

    total: int

    source: str = "knowledge-service"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "items": self.items,
            "total": self.total,
            "source": self.source,
        }


class KnowledgeTool:
    """
    Knowledge Service Tool。

    默认连接：

        http://127.0.0.1:8001

    实际地址可以通过 constructor 配置。
    """

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8001",
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def search(
        self,
        request: KnowledgeSearchRequest,
    ) -> KnowledgeSearchResult:
        """
        搜索知识库。
        """
        if not request.query.strip():
            raise KnowledgeToolError(
                "query 不能为空"
            )

        if request.top_k <= 0:
            raise KnowledgeToolError(
                "top_k 必须大于 0"
            )

        payload: dict[str, Any] = {
            "query": request.query,
            "top_k": request.top_k,
        }

        if request.version:
            payload["version"] = (
                request.version
            )

        if request.source:
            payload["source"] = request.source

        if request.filters:
            payload["filters"] = (
                request.filters
            )

        url = (
            f"{self.base_url}"
            "/api/search"
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.post(
                    url,
                    json=payload,
                )

                response.raise_for_status()

        except httpx.HTTPError as exc:
            raise KnowledgeToolError(
                f"Knowledge Service 请求失败：{exc}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise KnowledgeToolError(
                "Knowledge Service 返回的数据不是有效 JSON"
            ) from exc

        items = data.get(
            "items",
            data.get(
                "results",
                [],
            ),
        )

        if not isinstance(items, list):
            items = []

        return KnowledgeSearchResult(
            query=request.query,
            items=items,
            total=len(items),
        )

    async def search_text(
        self,
        query: str,
        *,
        top_k: int = 5,
        version: str | None = None,
    ) -> KnowledgeSearchResult:
        """
        简化检索接口。
        """
        return await self.search(
            KnowledgeSearchRequest(
                query=query,
                top_k=top_k,
                version=version,
            )
        )


__all__ = [
    "KnowledgeTool",
    "KnowledgeSearchRequest",
    "KnowledgeSearchResult",
    "KnowledgeToolError",
]