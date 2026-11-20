from typing import Any

import re

from pydantic import BaseModel, Field, field_validator


# 页面上下文字段只允许安全文本：去控制字符、trim、限长 200（与前端白名单规则对齐）。
_PAGE_CONTEXT_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_PAGE_CONTEXT_MAX_LENGTH = 200

# W5：侧翼可携带的本页实体类型白名单；未知类型一律丢弃，避免任意字符串进入提示与审计。
_ENTITY_TYPES = frozenset(
    {
        "alert",
        "event",
        "finding",
        "device",
        "doc",
        "incident",
        "server",
        "connection",
        "diagnostic",
    }
)
_MAX_SNAPSHOT_KEYS = 20
_MAX_SNAPSHOT_VALUE = 300


class PageContext(BaseModel):

    """页面上下文（只读参考信息，非指令）：前端上报的当前页面路径、栏目与本页实体。

    服务端仅按固定模板回填白名单字段进 system 提示，绝不拼接页面 DOM 内容，
    也不把其中的文字当作指令执行。W5 起支持 entity（type + id）与 snapshot（只读摘要，
    仅存不进提示词），用于侧翼"带着本页实体提问"。
    """

    path: str = ""

    section: str = ""

    entity: dict[str, str] | None = None

    snapshot: dict[str, Any] | None = None

    @field_validator("path", "section", mode="before")
    @classmethod
    def _sanitize(cls, value):

        if not isinstance(value, str):

            raise ValueError("页面上下文字段必须是字符串")

        cleaned = _PAGE_CONTEXT_CONTROL_CHARS.sub("", value.strip())

        return cleaned[:_PAGE_CONTEXT_MAX_LENGTH]

    @field_validator("entity", mode="before")
    @classmethod
    def _sanitize_entity(cls, value):

        if value is None:
            return None

        if not isinstance(value, dict):
            raise ValueError("entity 必须是对象")

        entity_type = _PAGE_CONTEXT_CONTROL_CHARS.sub(
            "", str(value.get("type", "")).strip()
        ).lower()[:64]
        entity_id = _PAGE_CONTEXT_CONTROL_CHARS.sub(
            "", str(value.get("id", "")).strip()
        )[:_PAGE_CONTEXT_MAX_LENGTH]

        # 类型不在白名单或 id 为空：按"未带实体"处理，而不是报错阻断对话。
        if not entity_type or not entity_id or entity_type not in _ENTITY_TYPES:
            return None

        return {"type": entity_type, "id": entity_id}

    @field_validator("snapshot", mode="before")
    @classmethod
    def _sanitize_snapshot(cls, value):

        if value is None:
            return None

        if not isinstance(value, dict):
            raise ValueError("snapshot 必须是对象")

        cleaned: dict[str, Any] = {}
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= _MAX_SNAPSHOT_KEYS:
                break

            key = _PAGE_CONTEXT_CONTROL_CHARS.sub("", str(raw_key).strip())[:64]
            if not key or raw_value is None:
                continue

            if isinstance(raw_value, str):
                item = _PAGE_CONTEXT_CONTROL_CHARS.sub("", raw_value.strip())[:_MAX_SNAPSHOT_VALUE]
            elif isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
                item = raw_value
            elif isinstance(raw_value, bool):
                item = raw_value
            else:
                continue

            if item == "":
                continue

            cleaned[key] = item

        return cleaned or None


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

    # 图像证据文件名（最多 5 张），用于展示/审计/路由信号，不含像素内容。
    images: list[str] = Field(
        default_factory=list,
        max_length=5,
    )

    # 真实图像内容：data URL（data:image/...;base64,...）或裸 base64，最多 5 张。
    # 仅当该项非空时才走视觉模型真实识别；images 只有文件名时仍为旧的文本链路。
    image_data: list[str] = Field(
        default_factory=list,
        max_length=5,
    )

    # 页面上下文（可选）：前端上报的当前页面路径与栏目，仅作回答参考信息；
    # 未传时（None）行为与旧版完全一致。
    context: PageContext | None = None

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

    # GUARDRAIL v1：本次对话的护栏处置结果（NONE/ALLOW/REDACT/BLOCK）。
    # 默认 NONE 保持向后兼容；前端不展示（D2 裁决），仅入审计与元数据。
    guard_action: str = "NONE"

    citations: list[Citation] = Field(
        default_factory=list
    )

    evidence: list[dict[str, Any]] = Field(
        default_factory=list
    )

    # W2：安全意识结构化简报（smartops.security_brief.v1）。
    # 由确定性规则生成；生成失败时为 None，不阻断对话主链路。
    security_brief: dict[str, Any] | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )