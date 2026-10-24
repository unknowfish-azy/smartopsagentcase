from typing import Any

from ..core.config import settings
from ..core.exceptions import RAGException


class RAGService:
    """
    RAG 编排服务。

    AI Service 不直接实现 BM25 / Vector / Reranker，
    而是通过统一接口调用 Knowledge。
    """

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        version: str | None = None,
    ) -> dict[str, Any]:

        # 当前阶段允许 Knowledge 尚未启动。
        # 不影响 AI Service 本身启动。
        try:
            import httpx
        except ImportError as exc:
            raise RAGException(
                "未安装 httpx"
            ) from exc

        payload = {
            "query": query,
            "top_k": top_k,
            "version": version,
        }

        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout
            ) as client:

                response = await client.post(
                    (
                        f"{settings.knowledge_service_url}"
                        "/api/search"
                    ),
                    json=payload,
                )

        except Exception:
            return self._empty_result(
                query
            )

        if response.status_code != 200:
            return self._empty_result(
                query
            )

        data = response.json()

        return data

    @staticmethod
    def _empty_result(
        query: str,
    ):

        return {
            "query": query,
            "results": [],
            "evidences": [],
            "citations": [],
            "trust_score": 0.0,
        }

    @staticmethod
    def build_context(
        results: list[dict[str, Any]],
    ) -> str:

        if not results:
            return (
                "当前没有检索到可用知识证据。"
            )

        sections = []

        for index, result in enumerate(
            results,
            start=1,
        ):

            content = result.get(
                "content",
                "",
            )

            source = result.get(
                "source",
                "",
            )

            version = result.get(
                "version",
                "latest",
            )

            sections.append(
                f"[证据 {index}]\n"
                f"来源：{source}\n"
                f"版本：{version}\n"
                f"内容：{content}"
            )

        return "\n\n".join(sections)