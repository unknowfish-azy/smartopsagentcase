import logging
import sys
from pathlib import Path
from uuid import uuid4

# CLI may start in ai-service/; the shared contract lives beside that package.
repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
from agent.runtime_events import RunIdentity, terminal_event

from ..core.exceptions import LLMException, UpstreamSaturated
from ..core.context_budget import (
    ContextBudget,
    ModelRouter,
    RagQueryCache,
)
from ..schemas.chat import (
    ChatRequest,
    ChatResponse,
    Citation,
)
from .llm import LLMService
from .rag import RAGService


logger = logging.getLogger(__name__)

# PERF-07：检索缓存必须是进程级共享——ChatService 按请求新建实例，
# 实例级缓存永远命中不了。这里惰性构建一次，全进程复用。
_shared_rag_cache: "RagQueryCache | None" = None


def _get_shared_rag_cache() -> "RagQueryCache":
    global _shared_rag_cache
    if _shared_rag_cache is None:
        from ..core.config import settings
        _shared_rag_cache = RagQueryCache(
            ttl_sec=settings.rag_cache_ttl_sec,
            max_entries=settings.rag_cache_max_entries,
        )
    return _shared_rag_cache

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

        # PERF-07：上下文预算与模型路由（本实例构造即读取当前配置）；
        # 检索缓存进程级共享（见 _get_shared_rag_cache）。
        from ..core.config import settings

        self._budget = ContextBudget(
            budget_chars=settings.context_budget_chars,
        )
        self._router = ModelRouter(
            default_model=settings.llm_model,
            simple_model=settings.llm_model_simple,
            complex_model=settings.llm_model_complex,
        )
        self._rag_cache = _get_shared_rag_cache()

    async def _retrieve_with_cache(
        self,
        request: ChatRequest,
        identity: RunIdentity,
    ) -> tuple[dict, dict]:
        """RAG 检索 + PERF-07 缓存。

        缓存键包含租户/用户/角色（权限）、知识版本与全部检索参数；
        降级或失败的检索结果不进缓存。返回 (rag_data, cache_metadata)。
        """
        meta = request.metadata or {}
        key = RagQueryCache.make_key(
            request.message,
            tenant=str(meta.get("tenant_id", "")),
            user=str(meta.get("user_id", "")),
            role=str(meta.get("role", "")),
            version=request.version,
            top_k=request.top_k,
            source=request.source,
            score_threshold=request.score_threshold,
            vector_weight=request.vector_weight,
            bm25_weight=request.bm25_weight,
        )
        cached = self._rag_cache.get(key)
        if cached is not None:
            return cached, {"rag_cache": "hit", **self._rag_cache.stats_dict()}
        rag_data = await self.rag.retrieve(
            query=request.message,
            top_k=request.top_k,
            version=request.version,
            source=request.source,
            score_threshold=request.score_threshold,
            vector_weight=request.vector_weight,
            bm25_weight=request.bm25_weight,
            request_id=identity.request_id,
            task_id=identity.task_id,
            run_id=identity.run_id,
        )
        self._rag_cache.put(key, rag_data)
        return rag_data, {"rag_cache": "miss", **self._rag_cache.stats_dict()}

    async def chat(
        self,
        request: ChatRequest,
        identity: RunIdentity | None = None,
    ) -> ChatResponse:

        identity = identity or RunIdentity.create(request_id=request.metadata.get("request_id"), task_id=request.metadata.get("task_id"))
        logger.info(
            "chat.start request_id=%s task_id=%s run_id=%s mode=blocking",
            identity.request_id, identity.task_id, identity.run_id,
        )
        conversation_id = (
            request.conversation_id
            or str(uuid4())
        )

        rag_data = {
            "results": [],
            "citations": [],
            "trust_score": 0.0,
        }

        rag_status = "disabled"
        cache_metadata: dict = {"rag_cache": "disabled"}

        if request.use_rag:

            rag_data, cache_metadata = await self._retrieve_with_cache(request, identity)
            rag_status = self._rag_metadata(request, rag_data)["rag_status"]
            logger.info(
                "chat.rag request_id=%s task_id=%s run_id=%s status=%s results=%s cache=%s",
                identity.request_id, identity.task_id, identity.run_id,
                rag_status, len(rag_data.get("results", [])), cache_metadata["rag_cache"],
            )

        results = rag_data.get(
            "results",
            [],
        )

        # PERF-07：证据过字符预算（分数优先装填），超预算的丢弃与截断如实记账。
        budgeted_results, budget_stats = self._budget.apply(results)

        context = self.rag.build_context(
            budgeted_results
        )

        prompt = self._build_prompt(
            message=request.message,
            context=context,
            images=request.images,
        )

        # PERF-07：按复杂度路由模型；未配置路由模型时如实沿用全局模型。
        routing = self._router.route(
            request.message,
            images=request.images,
            evidence_count=len(budgeted_results),
            verification_required=(request.metadata or {}).get("verification_required") is True,
        )

        answer = await self.llm.generate(
            prompt,
            system_prompt=SYSTEM_PROMPT,
            model=routing.model,
        )

        inspection = self._inspect_request(request, rag_data)

        citations = [
            Citation(
                citation_id=item.get(
                    "citation_id",
                    index,
                ),
                title=item.get(
                    "title",
                    "",
                ),
                snippet=item.get(
                    "snippet",
                    "",
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

        logger.info(
            "chat.terminal request_id=%s task_id=%s run_id=%s status=succeeded rag_status=%s",
            identity.request_id, identity.task_id, identity.run_id, rag_status,
        )

        return ChatResponse(
            answer=answer,
            conversation_id=conversation_id,
            model=routing.model,
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
                "run_event": terminal_event(identity, "ai-service", "succeeded"),
                "rag_enabled": request.use_rag,
                "top_k": request.top_k,
                "version": request.version,
                "images": request.images,
                "degraded": self.llm.degraded,
                "effective_provider": self.llm.effective_provider,
                "degradation_reason": self.llm.degradation_reason,
                **self._rag_metadata(request, rag_data),
                **({"inspection": inspection} if inspection else {}),
                "model_routing": self._router.decision_dict(routing),
                "context_budget": self._budget.stats_dict(budget_stats),
                **cache_metadata,
            },
        )

    async def chat_stream(
        self,
        request: ChatRequest,
        identity: RunIdentity | None = None,
    ):
        identity = identity or RunIdentity.create(request_id=request.metadata.get("request_id"), task_id=request.metadata.get("task_id"))
        logger.info(
            "chat.start request_id=%s task_id=%s run_id=%s mode=stream",
            identity.request_id, identity.task_id, identity.run_id,
        )
        status = "failed"
        code = "CHAT_PIPELINE_FAILED"
        degraded = False
        provider = "-"
        yield {"event": "run", "data": terminal_event(identity, "ai-service", "started")}
        try:
            async for event in self._chat_stream(request, identity):
                if event["event"] == "done":
                    status, code = "succeeded", "-"
                    metadata = event["data"].get("metadata", {})
                    degraded = bool(metadata.get("degraded"))
                    provider = metadata.get("effective_provider") or "-"
                elif event["event"] == "error":
                    status = "failed"
                    code = event["data"].get("code", "AI_ERROR")
                if event["event"] in {"done", "error"}:
                    record = terminal_event(identity, "ai-service", "failed" if event["event"] == "error" else "succeeded")
                    if event["event"] == "done":
                        event["data"]["metadata"]["run_event"] = record
                    else:
                        event["data"]["run_event"] = record
                yield event
        except Exception:
            status, code = "failed", "CHAT_PIPELINE_FAILED"
            yield {"event": "error", "data": {
                "code": "CHAT_PIPELINE_FAILED", "message": "对话处理失败，请根据运行编号复查服务日志",
                "run_event": terminal_event(identity, "ai-service", "failed"),
            }}
        finally:
            logger.info(
                "chat.terminal request_id=%s task_id=%s run_id=%s status=%s code=%s degraded=%s provider=%s",
                identity.request_id, identity.task_id, identity.run_id, status, code, degraded, provider,
            )

    async def _chat_stream(
        self,
        request: ChatRequest,
        identity: RunIdentity,
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

        cache_metadata: dict = {"rag_cache": "disabled"}

        if request.use_rag:
            rag_data, cache_metadata = await self._retrieve_with_cache(request, identity)
            rag_meta = self._rag_metadata(request, rag_data)
            logger.info(
                "chat.rag request_id=%s task_id=%s run_id=%s status=%s results=%s cache=%s degraded=%s reason=%s",
                identity.request_id, identity.task_id, identity.run_id,
                rag_meta["rag_status"], len(rag_data.get("results", [])),
                cache_metadata["rag_cache"],
                rag_meta["rag_degraded"], rag_meta["rag_degradation_reason"] or "-",
            )

        results = rag_data.get("results", [])
        # PERF-07：证据过字符预算（分数优先装填）。
        budgeted_results, budget_stats = self._budget.apply(results)
        context = self.rag.build_context(budgeted_results)
        prompt = self._build_prompt(
            message=request.message,
            context=context,
            images=request.images,
        )

        # PERF-07：按复杂度路由模型；未配置路由模型时如实沿用全局模型。
        routing = self._router.route(
            request.message,
            images=request.images,
            evidence_count=len(budgeted_results),
            verification_required=(request.metadata or {}).get("verification_required") is True,
        )

        # Report only stages actually performed by this chat path.
        thinking_steps = []
        if request.images:
            thinking_steps.append(
                {"stage": "attachments", "label": "附件已接收", "detail": f"收到 {len(request.images)} 个图像文件名，尚未执行图像识别"}
            )
        if request.use_rag:
            rag_metadata = self._rag_metadata(request, rag_data)
            thinking_steps.append({
                "stage": "retrieve", "label": "知识检索结果",
                "detail": f"状态：{rag_metadata['rag_status']}；返回 {len(results)} 条知识片段",
            })
        thinking_steps.append({"stage": "answer", "label": "生成回答", "detail": "根据当前可用信息生成回答"})
        for step in thinking_steps:
            yield {"event": "thinking", "data": step}

        # 2) 流式 token
        try:
            async for delta in self.llm.generate_stream(
                prompt,
                system_prompt=SYSTEM_PROMPT,
                model=routing.model,
            ):
                yield {"event": "token", "data": {"delta": delta}}
        except UpstreamSaturated:
            # 容量不足是明确的过载状态：终止本次流式，不混入 mock 输出。
            yield {"event": "error", "data": {
                "code": "UPSTREAM_SATURATED",
                "message": "上游容量已饱和，请稍后重试",
            }}
            return
        except LLMException:
            yield {"event": "error", "data": {
                "code": "LLM_STREAM_INTERRUPTED",
                "message": "模型输出中断，已保留部分回答，请重试",
            }}
            return

        inspection = self._inspect_request(request, rag_data)
        if inspection:
            yield {"event": "inspection", "data": inspection}

        # 3) 完成事件
        citations = [
            Citation(
                citation_id=item.get("citation_id", index),
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
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
                "model": routing.model,
                "provider": self._get_provider(),
                "trust_score": float(rag_data.get("trust_score", 0.0)),
                "citations": [c.model_dump() for c in citations],
                "evidence": rag_data.get("evidences", []),
                "metadata": {
                    "rag_enabled": request.use_rag,
                    "top_k": request.top_k,
                    "version": request.version,
                    "images": request.images,
                    "degraded": self.llm.degraded,
                    "effective_provider": self.llm.effective_provider,
                    "degradation_reason": self.llm.degradation_reason,
                    **self._rag_metadata(request, rag_data),
                    **({"inspection": inspection} if inspection else {}),
                    "model_routing": self._router.decision_dict(routing),
                    "context_budget": self._budget.stats_dict(budget_stats),
                    **cache_metadata,
                },
            },
        }

    @staticmethod
    def _rag_metadata(request: ChatRequest, rag_data: dict) -> dict:
        return {
            "rag_status": (
                rag_data.get("retrieval_status", "ok" if rag_data.get("results") else "empty")
                if request.use_rag else "disabled"
            ),
            "rag_degraded": bool(rag_data.get("degraded", False)) if request.use_rag else False,
            "rag_degradation_reason": rag_data.get("degradation_reason", "") if request.use_rag else "",
        }

    @staticmethod
    def _inspect_request(request: ChatRequest, rag_data: dict) -> dict | None:
        """Run the real four-level inspector for agent execution metadata."""
        metadata = request.metadata or {}
        if "agent_claim" not in metadata and "actual_state" not in metadata and metadata.get("verification_required") is not True:
            return None

        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from agent.inspector.models import EvidenceItem, ToolCallRecord
        from agent.inspector.pipeline import InspectorPipeline

        raw_evidence = metadata.get("evidence") or rag_data.get("evidences") or []
        evidence = [
            item if isinstance(item, EvidenceItem) else EvidenceItem(
                content=str(item.get("content", "")),
                source=str(item.get("source", "")),
                version=str(item.get("version", "latest")),
                score=float(item.get("score", 0.0)),
            )
            for item in raw_evidence
            if isinstance(item, dict) or isinstance(item, EvidenceItem)
        ]
        raw_calls = metadata.get("tool_calls") or []
        tool_calls = [
            item if isinstance(item, ToolCallRecord) else ToolCallRecord(
                tool_name=str(item.get("tool_name", "")),
                risk=str(item.get("risk", "LOW")),
                approval_granted=bool(item.get("approval_granted", False)),
                success=bool(item.get("success", False)),
                args=item.get("args") or {},
            )
            for item in raw_calls
            if isinstance(item, dict) or isinstance(item, ToolCallRecord)
        ]
        context = {
            "task_id": metadata.get("task_id", request.conversation_id or "chat"),
            "target": metadata.get("target", "AGENT"),
            "agent_claim": metadata.get("agent_claim"),
            "actual_state": metadata.get("actual_state"),
            "evidence": evidence,
            "tool_calls": tool_calls,
            "policy": metadata.get("policy") or {},
            "environment_version": metadata.get("environment_version"),
            "metadata": {
                "source": "ai-service.chat",
                "verification_required": metadata.get("verification_required") is True,
            },
        }
        return InspectorPipeline().run(context).to_dict()

    @staticmethod
    def _build_prompt(
        message: str,
        context: str,
        images: list[str] | None = None,
    ) -> str:

        image_section = ""
        if images:
            lines = "\n".join(
                f"- {name}" for name in images
            )
            image_section = f"""
图像证据（用户提供的截图/拍照，当前阶段仅提供文件名）：
{lines}
"""

        return f"""
请回答下面的用户问题。

用户问题：
{message}
{image_section}
知识库证据：
{context}

要求：
- 优先使用知识库证据。
- 不要把没有证据支持的内容说成确定事实。
- 如果知识库没有足够证据，请明确说明。
- 如果涉及执行操作，只给出建议，不声称已经执行。
"""

    @staticmethod
    def _get_provider():

        from ..core.config import settings

        return settings.llm_provider
