import math
from typing import Any

from ..schemas.chat import Citation

from ..core.config import settings
from ..core.correlation import correlation_headers
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
        source: str | None = None,
        score_threshold: float | None = None,
        vector_weight: float | None = None,
        bm25_weight: float | None = None,
        request_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:

        # 当前阶段允许 Knowledge 尚未启动。
        # 不影响 AI Service 本身启动。
        try:
            import httpx
        except ImportError as exc:
            raise RAGException(
                "未安装 httpx"
            ) from exc

        # 只显式填入非 None 字段，让 knowledge 服务侧按 "None = 用默认值" 的约定处理。
        payload: dict[str, Any] = {
            "query": query,
            "top_k": top_k,
        }
        if version is not None:
            payload["version"] = version
        if source is not None:
            payload["source"] = source
        if score_threshold is not None:
            payload["score_threshold"] = score_threshold
        if vector_weight is not None:
            payload["vector_weight"] = vector_weight
        if bm25_weight is not None:
            payload["bm25_weight"] = bm25_weight

        # Knowledge 开启鉴权后必须带上 X-API-Key，否则会拿到 401。
        headers: dict[str, str] = {}
        if settings.knowledge_api_key:
            headers["X-API-Key"] = settings.knowledge_api_key
        headers.update(correlation_headers(request_id, task_id, run_id))

        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout,
                trust_env=False,
            ) as client:

                response = await client.post(
                    (
                        f"{settings.knowledge_service_url}"
                        "/api/search"
                    ),
                    json=payload,
                    headers=headers,
                )

        except httpx.HTTPError:
            return self._empty_result(query, status="unavailable", reason="knowledge_transport_error")

        if response.status_code != 200:
            return self._empty_result(query, status="unavailable", reason=f"knowledge_http_{response.status_code}")

        try:
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise ValueError("Invalid search result")
            for key in ("results", "citations", "evidences"):
                items = data.get(key, [])
                if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                    raise ValueError("Invalid evidence list")
            for item in data["results"]:
                for key in ("content", "source"):
                    if key in item and not isinstance(item[key], str):
                        raise ValueError("Invalid evidence text")
            for index, citation in enumerate(data.get("citations", []), start=1):
                validated = Citation.model_validate({"citation_id": index, "source": "", "chunk_id": "", **citation})
                if not math.isfinite(validated.score):
                    raise ValueError("Invalid citation score")
            for evidence in data.get("evidences", []):
                if not math.isfinite(float(evidence.get("score", 0.0))):
                    raise ValueError("Invalid evidence score")
            score = float(data.get("trust_score", 0.0))
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                raise ValueError("Invalid trust score")
        except (TypeError, ValueError):
            return self._empty_result(query, status="invalid_response", reason="knowledge_invalid_response")

        return {
            **data,
            "trust_score": score,
            "retrieval_status": "ok" if data["results"] else "empty",
            "degraded": False,
            "degradation_reason": "",
        }

    @staticmethod
    def _empty_result(
        query: str,
        *,
        status: str = "empty",
        reason: str = "",
    ):

        return {
            "query": query,
            "results": [],
            "evidences": [],
            "citations": [],
            "trust_score": 0.0,
            "retrieval_status": status,
            "degraded": bool(reason),
            "degradation_reason": reason,
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
