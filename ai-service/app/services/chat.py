import asyncio
from uuid import uuid4

from ..schemas.chat import (
    ChatRequest,
    ChatResponse,
    Citation,
)
from .llm import LLMService
from .rag import RAGService


SYSTEM_PROMPT = """
你是智维Agent的AI运维助手。

请遵循以下原则：

1. 优先依据提供的知识证据回答。
2. 不要编造不存在的事实。
3. 无法确认时明确说明。
4. 涉及高风险运维操作时，不要直接声称已经执行。
5. 尽量给出清晰、可验证的步骤。
6. 回答应该考虑知识版本。
"""


class ChatService:

    def __init__(
        self,
        llm_service: LLMService | None = None,
        rag_service: RAGService | None = None,
    ):

        self.llm = (
            llm_service
            or LLMService()
        )

        self.rag = (
            rag_service
            or RAGService()
        )

    async def chat(
        self,
        request: ChatRequest,
    ) -> ChatResponse:

        conversation_id = (
            request.conversation_id
            or str(uuid4())
        )

        rag_data = {
            "results": [],
            "citations": [],
            "trust_score": 0.0,
        }

        if request.use_rag:

            rag_data = await self.rag.retrieve(
                query=request.message,
                top_k=request.top_k,
                version=request.version,
            )

        results = rag_data.get(
            "results",
            [],
        )

        context = self.rag.build_context(
            results
        )

        prompt = self._build_prompt(
            message=request.message,
            context=context,
        )

        answer = await self.llm.generate(
            prompt,
            system_prompt=SYSTEM_PROMPT,
        )

        citations = [
            Citation(
                citation_id=item.get(
                    "citation_id",
                    index,
                ),
                source=item.get(
                    "source",
                    "",
                ),
                chunk_id=item.get(
                    "chunk_id",
                    "",
                ),
                version=item.get(
                    "version",
                ),
                score=float(
                    item.get(
                        "score",
                        0.0,
                    )
                ),
            )
            for index, item in enumerate(
                rag_data.get(
                    "citations",
                    [],
                ),
                start=1,
            )
        ]

        return ChatResponse(
            answer=answer,
            conversation_id=conversation_id,
            model=(
                self._get_model_name()
            ),
            provider=(
                self._get_provider()
            ),
            trust_score=float(
                rag_data.get(
                    "trust_score",
                    0.0,
                )
            ),
            citations=citations,
            evidence=rag_data.get(
                "evidences",
                [],
            ),
            metadata={
                "rag_enabled": request.use_rag,
                "top_k": request.top_k,
                "version": request.version,
            },
        )

    async def chat_stream(
        self,
        request: ChatRequest,
    ):
        """流式对话：产出 SSE 事件（thinking / token / done），用于前端 AI 思考可视化。"""

        conversation_id = (
            request.conversation_id
            or str(uuid4())
        )

        rag_data: dict = {
            "results": [],
            "citations": [],
            "trust_score": 0.0,
        }

        if request.use_rag:
            rag_data = await self.rag.retrieve(
                query=request.message,
                top_k=request.top_k,
                version=request.version,
            )

        results = rag_data.get("results", [])
        context = self.rag.build_context(results)
        prompt = self._build_prompt(
            message=request.message,
            context=context,
        )

        # 1) AI 思考过程事件（驱动前端可视化）
        thinking_steps = [
            {"stage": "retrieve", "label": "知识检索", "detail": f"检索知识库 top_k={request.top_k}"},
            {"stage": "evidence", "label": "证据验证", "detail": f"命中 {len(rag_data.get('citations', []))} 条证据"},
            {"stage": "plan", "label": "Agent 规划", "detail": "将故障拆解为可执行步骤"},
            {"stage": "risk", "label": "风险判定", "detail": "策略引擎评估操作风险"},
            {"stage": "answer", "label": "生成回答", "detail": "基于证据生成可信回答"},
        ]
        for step in thinking_steps:
            yield {"event": "thinking", "data": step}
            await asyncio.sleep(0.15)

        # 2) 流式 token
        async for delta in self.llm.generate_stream(
            prompt,
            system_prompt=SYSTEM_PROMPT,
        ):
            yield {"event": "token", "data": {"delta": delta}}

        # 3) 完成事件
        citations = [
            Citation(
                citation_id=item.get("citation_id", index),
                source=item.get("source", ""),
                chunk_id=item.get("chunk_id", ""),
                version=item.get("version"),
                score=float(item.get("score", 0.0)),
            )
            for index, item in enumerate(
                rag_data.get("citations", []),
                start=1,
            )
        ]

        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation_id,
                "model": self._get_model_name(),
                "provider": self._get_provider(),
                "trust_score": float(rag_data.get("trust_score", 0.0)),
                "citations": [c.model_dump() for c in citations],
                "evidence": rag_data.get("evidences", []),
                "metadata": {
                    "rag_enabled": request.use_rag,
                    "top_k": request.top_k,
                    "version": request.version,
                },
            },
        }

    @staticmethod
    def _build_prompt(
        message: str,
        context: str,
    ) -> str:

        return f"""
请回答下面的用户问题。

用户问题：
{message}

知识库证据：
{context}

要求：
- 优先使用知识库证据。
- 不要把没有证据支持的内容说成确定事实。
- 如果知识库没有足够证据，请明确说明。
- 如果涉及执行操作，只给出建议，不声称已经执行。
"""

    @staticmethod
    def _get_model_name():

        from ..core.config import settings

        return settings.llm_model

    @staticmethod
    def _get_provider():

        from ..core.config import settings

        return settings.llm_provider