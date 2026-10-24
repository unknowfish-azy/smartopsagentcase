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