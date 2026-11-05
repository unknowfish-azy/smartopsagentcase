from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):

    message: str = Field(
        min_length=1,
        max_length=10000,
    )

    conversation_id: str | None = None

    use_rag: bool = True

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    version: str | None = None

    # 以下字段全部可选，默认 None 表示沿用 knowledge 服务默认值。
    # 由后端/前端在"检索调试"场景下显式传入。
    source: str | None = None
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    bm25_weight: float | None = Field(default=None, ge=0.0, le=1.0)

    # 图像证据（文件名列表，最多 5 张）。
    # 当前阶段仅传递文件名用于模拟解析，图像内容不上传。
    images: list[str] = Field(
        default_factory=list,
        max_length=5,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class Citation(BaseModel):

    citation_id: int

    title: str = ""

    snippet: str = ""

    source: str

    chunk_id: str

    version: str | None = None

    score: float = 0.0


class ChatResponse(BaseModel):

    answer: str

    conversation_id: str

    model: str

    provider: str

    trust_score: float = 0.0

    citations: list[Citation] = Field(
        default_factory=list
    )

    evidence: list[dict[str, Any]] = Field(
        default_factory=list
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )