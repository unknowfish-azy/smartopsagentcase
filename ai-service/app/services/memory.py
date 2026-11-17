"""对话记忆闭环：召回用户已沉淀的经验，回写用户明确教给的规则。

分层约束：ai-service 不直连数据库。operator_memory 的读写统一走 Java 的
``/api/internal/memory/{recall,remember}`` 内部接口（X-SmartOps-Internal-Token），
用户归属由 Java 签发的 run 令牌 subject 决定，不接受客户端自报的 userId。

失败策略是 fail-open：记忆是增强项，Java 未启动、token 未配置或接口超时都只
记日志并返回空结果，绝不影响本次对话。
"""

from __future__ import annotations

import hashlib
import logging
import re

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

# 只认「用户明确教一条以后要遵守的规则」，普通问答一律不写。
# 每轮都回写会把 operator_memory 变成聊天记录垃圾桶，召回时全是噪声。
_PREFERENCE_PATTERNS = (
    re.compile(
        r"以后遇到(?P<incident>[^，,。；;！!？?]{2,40})[，,、]?\s*"
        r"(?:先|就|要|请)(?P<action>[^。；;！!？?]{2,80})"
    ),
    re.compile(r"以后(?:都|统一|一律)(?P<action>[^。；;！!？?]{4,80})"),
)

_GENERIC_INCIDENT = "通用约定"
MAX_INCIDENT_CHARS = 40
MAX_ACTION_CHARS = 120
MAX_QUERY_CHARS = 500
SOURCE_PREFIX = "chat-pref:"


def _clean(value: str | None) -> str:
    return re.sub(r"^[\s：:，,、]+|[\s。.!！?？]+$", "", value or "")


class MemoryService:
    """operator_memory 的 HTTP 客户端 + 记忆注入/提取规则。"""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._base_url = (settings.memory_service_url if base_url is None else base_url).rstrip("/")
        self._token = settings.memory_internal_token if token is None else token
        self._timeout = settings.memory_timeout_sec if timeout is None else timeout
        self._enabled = settings.memory_enabled if enabled is None else enabled

    @property
    def configured(self) -> bool:
        return bool(self._enabled and self._base_url and self._token)

    async def recall(self, user_id: str | int | None, query: str, limit: int | None = None) -> list[dict]:
        """召回「incident_key 被这句话包含」的活跃记忆。"""
        if not self.configured or not user_id or not (query or "").strip():
            return []
        data = await self._post(
            "/api/internal/memory/recall",
            {
                "userId": self._as_user_id(user_id),
                "query": query.strip()[:MAX_QUERY_CHARS],
                "limit": settings.memory_recall_limit if limit is None else limit,
            },
        )
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    async def remember(
        self,
        user_id: str | int | None,
        incident_key: str,
        preferred_action: str,
        source_refs: str,
    ) -> dict | None:
        """回写一条聊天偏好；同一规则重复说由 Java 侧唯一键幂等处理。"""
        if not self.configured or not user_id:
            return None
        data = await self._post(
            "/api/internal/memory/remember",
            {
                "userId": self._as_user_id(user_id),
                "incidentKey": incident_key,
                "preferredAction": preferred_action,
                "sourceRefs": source_refs,
            },
        )
        return data if isinstance(data, dict) else None

    async def _post(self, path: str, payload: dict) -> object | None:
        if not self.configured:
            return None
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.post(
                    path,
                    json=payload,
                    headers={"X-SmartOps-Internal-Token": self._token},
                )
            response.raise_for_status()
            body = response.json()
        except Exception as failure:  # noqa: BLE001 - 记忆是增强项，任何失败都只降级
            logger.warning("memory.degraded path=%s reason=%s", path, failure)
            return None
        return body.get("data") if isinstance(body, dict) else None

    @staticmethod
    def _as_user_id(user_id: str | int) -> int | None:
        try:
            return int(str(user_id).strip())
        except (TypeError, ValueError):
            logger.warning("memory.degraded reason=USER_ID_NOT_NUMERIC")
            return None

    @staticmethod
    def render_section(memories: list[dict]) -> str:
        """把召回结果渲染成 prompt 片段；空列表返回空串（与无记忆时逐字节一致）。"""
        lines: list[str] = []
        for item in memories[: settings.memory_recall_limit]:
            incident = _clean(str(item.get("incidentKey") or ""))
            action = _clean(str(item.get("preferredAction") or ""))
            if not incident or not action:
                continue
            suffix = ""
            confidence = item.get("confidence")
            evidence_count = item.get("evidenceCount")
            if isinstance(confidence, (int, float)):
                suffix = f"（可信度 {float(confidence):.2f}，被引用 {int(evidence_count or 0)} 次）"
            lines.append(f"- 事件「{incident}」→ 处理偏好：{action}{suffix}")
        if not lines:
            return ""
        return (
            "\n历史记忆（用户此前确认过的偏好，可参考，但不等同知识库证据；"
            "与本次证据冲突时以证据为准并说明差异）：\n"
            + "\n".join(lines)
            + "\n"
        )

    @staticmethod
    def extract_preference(message: str) -> dict | None:
        """从用户话里抽取可回写的规则；抽不到就返回 None，绝不猜测补全。"""
        text = re.sub(r"\s+", " ", message or "").strip()
        if not 8 <= len(text) <= 300:
            return None
        # 问句不是规则（「以后遇到这个先看日志吗？」），不能当记忆写进去。
        if text.endswith(("？", "?")) or text.endswith("吗"):
            return None

        for pattern in _PREFERENCE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            action = _clean(match.group("action"))
            incident = _clean(match.groupdict().get("incident")) or _GENERIC_INCIDENT
            if len(action) < 4:
                continue
            digest = hashlib.sha256(f"{incident}|{action}".encode("utf-8")).hexdigest()
            return {
                "incident_key": incident[:MAX_INCIDENT_CHARS],
                "preferred_action": action[:MAX_ACTION_CHARS],
                "source_refs": SOURCE_PREFIX + digest[:16],
            }
        return None
